import math
import unittest

import pandas as pd

from src.processing.join_static import (
    attach_timetable,
    gtfs_time_to_seconds,
    match_trips,
    run_key,
    services_on_date,
    stop_schedule,
)


def _calendar():
    base = {"start_date": "20260901", "end_date": "20261231"}
    days = {d: "0" for d in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")}
    return pd.DataFrame([
        {"service_id": "A", **days, "monday": "1", **base},
        {"service_id": "B", **days, "saturday": "1", **base},
    ])


def _trips():
    return pd.DataFrame([
        {"trip_id": "0251-002-101-016:1000", "service_id": "A", "direction_id": "0", "trip_headsign": "Tallawong"},
        {"trip_id": "0253-002-101-016:1000", "service_id": "B", "direction_id": "0", "trip_headsign": "Tallawong"},
        {"trip_id": "0251-002-102-001:1000", "service_id": "A", "direction_id": "0", "trip_headsign": "Tallawong"},
        {"trip_id": "0252-001-102-001:1000", "service_id": "A", "direction_id": "0", "trip_headsign": "Tallawong"},
    ])


def _stop_times():
    return pd.DataFrame([
        {"trip_id": "0251-002-101-016:1000", "stop_id": "S1", "stop_sequence": "1", "arrival_time": "04:00:00"},
        {"trip_id": "0251-002-101-016:1000", "stop_id": "S2", "stop_sequence": "2", "arrival_time": "04:05:00"},
        {"trip_id": "0251-002-102-001:1000", "stop_id": "S1", "stop_sequence": "1", "arrival_time": "04:04:00"},
        {"trip_id": "0251-002-102-001:1000", "stop_id": "S2", "stop_sequence": "2", "arrival_time": "04:09:00"},
        {"trip_id": "0253-002-101-016:1000", "stop_id": "S1", "stop_sequence": "1", "arrival_time": "04:00:00"},
        {"trip_id": "0252-001-102-001:1000", "stop_id": "S1", "stop_sequence": "1", "arrival_time": "04:06:00"},
        {"trip_id": "0252-001-102-001:1000", "stop_id": "S9", "stop_sequence": "2", "arrival_time": "04:11:00"},
    ])


class HelpersTest(unittest.TestCase):
    def test_run_key_strips_revision_prefix(self):
        keys = run_key(pd.Series(["0241-001-101-016:1000", "0251-002-101-016:1000", "garbage"]))
        self.assertEqual(keys.iloc[0], "101-016")
        self.assertEqual(keys.iloc[1], "101-016")
        self.assertTrue(pd.isna(keys.iloc[2]))

    def test_gtfs_time_handles_hours_past_midnight(self):
        secs = gtfs_time_to_seconds(pd.Series(["04:05:00", "25:30:15"]))
        self.assertEqual(secs.iloc[0], 4 * 3600 + 5 * 60)
        self.assertEqual(secs.iloc[1], 25 * 3600 + 30 * 60 + 15)


class ServicesOnDateTest(unittest.TestCase):
    def test_weekday_column_and_date_range(self):
        empty = pd.DataFrame(columns=["service_id", "date", "exception_type"])
        self.assertEqual(services_on_date(_calendar(), empty, "20260907"), {"A"})
        self.assertEqual(services_on_date(_calendar(), empty, "20260905"), {"B"})
        self.assertEqual(services_on_date(_calendar(), empty, "20260808"), set())

    def test_calendar_dates_add_and_remove(self):
        exceptions = pd.DataFrame([
            {"service_id": "A", "date": "20260907", "exception_type": "2"},
            {"service_id": "B", "date": "20260907", "exception_type": "1"},
        ])
        self.assertEqual(services_on_date(_calendar(), exceptions, "20260907"), {"B"})


class MatchTripsTest(unittest.TestCase):
    def _match(self, trip_id, start_date):
        rt = pd.DataFrame([{"trip_id": trip_id, "start_date": start_date}])
        empty = pd.DataFrame(columns=["service_id", "date", "exception_type"])
        return match_trips(rt, _trips(), _calendar(), empty).iloc[0]

    def test_exact_match_wins(self):
        row = self._match("0251-002-101-016:1000", "20260907")
        self.assertEqual(row["static_trip_id"], "0251-002-101-016:1000")
        self.assertEqual(row["match_method"], "exact")

    def test_run_key_resolved_by_calendar(self):
        row = self._match("0241-001-101-016:1000", "20260907")
        self.assertEqual(row["static_trip_id"], "0251-002-101-016:1000")
        self.assertEqual(row["match_method"], "run_key_calendar")

    def test_run_key_picks_saturday_variant(self):
        row = self._match("0241-001-101-016:1000", "20260905")
        self.assertEqual(row["static_trip_id"], "0253-002-101-016:1000")

    def test_ambiguous_when_calendar_leaves_several(self):
        row = self._match("0241-001-102-001:1000", "20260907")
        self.assertEqual(row["static_trip_id"], "0251-002-102-001:1000")
        self.assertEqual(row["match_method"], "run_key_ambiguous")

    def test_falls_back_when_no_service_runs_that_day(self):
        row = self._match("0241-001-101-016:1000", "20261101")
        self.assertEqual(row["static_trip_id"], "0251-002-101-016:1000")
        self.assertEqual(row["match_method"], "run_key_no_calendar")

    def test_unmatched_when_run_key_unknown(self):
        row = self._match("0241-001-999-999:1000", "20260907")
        self.assertIsNone(row["static_trip_id"])
        self.assertEqual(row["match_method"], "unmatched")

    def _match_with_stop(self, trip_id, start_date, stop_id):
        rt = pd.DataFrame([{"trip_id": trip_id, "start_date": start_date, "stop_id": stop_id}])
        empty = pd.DataFrame(columns=["service_id", "date", "exception_type"])
        return match_trips(rt, _trips(), _calendar(), empty, _stop_times()).iloc[0]

    def test_observed_stop_breaks_ambiguity(self):
        row = self._match_with_stop("0241-001-102-001:1000", "20260907", "S9")
        self.assertEqual(row["static_trip_id"], "0252-001-102-001:1000")
        self.assertEqual(row["match_method"], "run_key_ambiguous")

    def test_observed_stop_breaks_no_calendar_fallback(self):
        row = self._match_with_stop("0241-001-102-001:1000", "20261101", "S9")
        self.assertEqual(row["static_trip_id"], "0252-001-102-001:1000")
        self.assertEqual(row["match_method"], "run_key_no_calendar")

    def test_lowest_id_when_stops_do_not_separate(self):
        row = self._match_with_stop("0241-001-102-001:1000", "20260907", "S1")
        self.assertEqual(row["static_trip_id"], "0251-002-102-001:1000")


class StopScheduleTest(unittest.TestCase):
    def setUp(self):
        self.sched = stop_schedule(_stop_times(), _trips()).set_index(["trip_id", "stop_id"])

    def test_position_and_fraction(self):
        first = self.sched.loc[("0251-002-101-016:1000", "S1")]
        last = self.sched.loc[("0251-002-101-016:1000", "S2")]
        self.assertEqual(first["stop_position"], 1)
        self.assertEqual(last["stop_position"], 2)
        self.assertEqual(first["n_stops_in_trip"], 2)
        self.assertEqual(first["frac_trip_complete"], 0.5)
        self.assertEqual(last["frac_trip_complete"], 1.0)

    def test_run_time_from_previous_stop(self):
        self.assertTrue(math.isnan(self.sched.loc[("0251-002-101-016:1000", "S1"), "sched_run_secs_from_prev"]))
        self.assertEqual(self.sched.loc[("0251-002-101-016:1000", "S2"), "sched_run_secs_from_prev"], 300)

    def test_headway_measured_within_one_service(self):
        self.assertTrue(math.isnan(self.sched.loc[("0251-002-101-016:1000", "S1"), "sched_headway_secs"]))
        self.assertEqual(self.sched.loc[("0251-002-102-001:1000", "S1"), "sched_headway_secs"], 240)
        self.assertTrue(math.isnan(self.sched.loc[("0253-002-101-016:1000", "S1"), "sched_headway_secs"]))


class AttachTimetableTest(unittest.TestCase):
    def test_joins_trip_stop_and_schedule_facts(self):
        rt = pd.DataFrame([
            {"trip_id": "0241-001-101-016:1000", "start_date": "20260907", "stop_id": "S2"},
            {"trip_id": "0241-001-999-999:1000", "start_date": "20260907", "stop_id": "S1"},
        ])
        stops = pd.DataFrame([
            {"stop_id": "S1", "stop_name": "Tallawong", "stop_lat": "-33.7", "stop_lon": "150.9"},
            {"stop_id": "S2", "stop_name": "Rouse Hill", "stop_lat": "-33.6", "stop_lon": "150.9"},
        ])
        empty = pd.DataFrame(columns=["service_id", "date", "exception_type"])
        match = match_trips(rt, _trips(), _calendar(), empty)
        out = attach_timetable(rt, match, _trips(), stops, stop_schedule(_stop_times(), _trips()))

        matched = out.iloc[0]
        self.assertEqual(matched["static_trip_id"], "0251-002-101-016:1000")
        self.assertEqual(matched["trip_headsign"], "Tallawong")
        self.assertEqual(matched["stop_name"], "Rouse Hill")
        self.assertEqual(matched["stop_position"], 2)
        self.assertEqual(matched["sched_run_secs_from_prev"], 300)

        unmatched = out.iloc[1]
        self.assertEqual(unmatched["stop_name"], "Tallawong")
        self.assertTrue(pd.isna(unmatched["static_trip_id"]))
        self.assertTrue(math.isnan(unmatched["stop_position"]))


if __name__ == "__main__":
    unittest.main()
