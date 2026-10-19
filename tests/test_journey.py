import unittest

import pandas as pd

from src.api.journey import clock, line_stations, live_only_departures, nearest_horizon, next_departures, station_names

# Three stations, two platforms each: A -> B -> C is direction 1, C -> A direction 0.
_STOPS = pd.DataFrame([
    {"stop_id": "A1", "stop_name": "Alpha Station, Platform 1"},
    {"stop_id": "A2", "stop_name": "Alpha Station, Platform 2"},
    {"stop_id": "B1", "stop_name": "Beta Station, Platform 1"},
    {"stop_id": "B2", "stop_name": "Beta Station, Platform 2"},
    {"stop_id": "C1", "stop_name": "Gamma Station, Platform 1"},
    {"stop_id": "C2", "stop_name": "Gamma Station, Platform 2"},
])

_DAYS = {d: "1" for d in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")}
_CALENDAR = pd.DataFrame([
    {"service_id": "DAILY", **_DAYS, "start_date": "20260101", "end_date": "20261231"},
    {"service_id": "OFF", **{d: "0" for d in _DAYS}, "start_date": "20260101", "end_date": "20261231"},
])
_CALENDAR_DATES = pd.DataFrame(columns=["service_id", "date", "exception_type"])


def _trip(trip_id, service_id, direction, headsign, calls):
    trip = {"trip_id": trip_id, "service_id": service_id, "direction_id": direction, "trip_headsign": headsign}
    times = [
        {"trip_id": trip_id, "stop_id": stop, "stop_sequence": str(seq), "arrival_time": t, "departure_time": t}
        for seq, (stop, t) in enumerate(calls, start=1)
    ]
    return trip, times


def _timetable(*trips):
    return pd.DataFrame([t for t, _ in trips]), pd.DataFrame([row for _, times in trips for row in times])


def _departures(trips, stop_times, now, from_station="Alpha Station", to_station="Gamma Station", **kwargs):
    return next_departures(
        from_station, to_station, pd.Timestamp(now, tz="Australia/Sydney"),
        _STOPS, trips, stop_times, _CALENDAR, _CALENDAR_DATES, **kwargs,
    )


class StationTest(unittest.TestCase):
    def test_platform_is_dropped(self):
        names = station_names(pd.Series(["Chatswood Station, Platform 2", "Central Station"]))
        self.assertEqual(list(names), ["Chatswood Station", "Central Station"])

    def test_line_order_follows_longest_direction_1_trip(self):
        trips, stop_times = _timetable(
            _trip("short", "DAILY", "1", "Beta", [("A1", "08:00:00"), ("B1", "08:05:00")]),
            _trip("full", "DAILY", "1", "Gamma", [("A1", "09:00:00"), ("B1", "09:05:00"), ("C1", "09:10:00")]),
            _trip("back", "DAILY", "0", "Alpha", [("C2", "09:00:00"), ("B2", "09:05:00"), ("A2", "09:10:00")]),
        )
        self.assertEqual(line_stations(_STOPS, trips, stop_times), ["Alpha Station", "Beta Station", "Gamma Station"])


class NextDeparturesTest(unittest.TestCase):
    def test_only_trains_heading_the_right_way(self):
        trips, stop_times = _timetable(
            _trip("out", "DAILY", "1", "Gamma", [("A1", "09:00:00"), ("B1", "09:05:00"), ("C1", "09:10:00")]),
            _trip("back", "DAILY", "0", "Alpha", [("C2", "09:00:00"), ("B2", "09:05:00"), ("A2", "09:10:00")]),
        )
        result = _departures(trips, stop_times, "2026-10-19 08:30")
        self.assertEqual(list(result["trip_id"]), ["out"])
        self.assertEqual(result.loc[0, "departure_seconds"], 9 * 3600)
        self.assertEqual(result.loc[0, "arrival_seconds"], 9 * 3600 + 10 * 60)
        self.assertEqual(result.loc[0, "origin_stop_sequence"], 1)

    def test_soonest_first_and_past_trains_dropped(self):
        trips, stop_times = _timetable(
            _trip("gone", "DAILY", "1", "Gamma", [("A1", "08:00:00"), ("C1", "08:10:00")]),
            _trip("later", "DAILY", "1", "Gamma", [("A1", "09:20:00"), ("C1", "09:30:00")]),
            _trip("next", "DAILY", "1", "Gamma", [("A1", "09:10:00"), ("C1", "09:20:00")]),
        )
        result = _departures(trips, stop_times, "2026-10-19 09:00")
        self.assertEqual(list(result["trip_id"]), ["next", "later"])

    def test_recently_scheduled_train_kept_within_grace(self):
        # It may be running late, so the caller decides with live data.
        trips, stop_times = _timetable(_trip("late", "DAILY", "1", "Gamma", [("A1", "09:00:00"), ("C1", "09:10:00")]))
        self.assertEqual(len(_departures(trips, stop_times, "2026-10-19 09:01")), 1)
        self.assertEqual(len(_departures(trips, stop_times, "2026-10-19 09:05")), 0)

    def test_services_not_running_today_excluded(self):
        trips, stop_times = _timetable(
            _trip("off", "OFF", "1", "Gamma", [("A1", "09:00:00"), ("C1", "09:10:00")]),
            _trip("on", "DAILY", "1", "Gamma", [("A1", "09:05:00"), ("C1", "09:15:00")]),
        )
        self.assertEqual(list(_departures(trips, stop_times, "2026-10-19 08:00")["trip_id"]), ["on"])

    def test_after_midnight_train_belongs_to_yesterday(self):
        # 24:30 on the 18th's timetable is 00:30 on the 19th; the 19th's own
        # run of the same daily trip comes a day later.
        trips, stop_times = _timetable(_trip("owl", "DAILY", "1", "Gamma", [("A1", "24:30:00"), ("C1", "24:40:00")]))
        result = _departures(trips, stop_times, "2026-10-19 00:10")
        self.assertEqual(list(result["service_date"]), ["20261018", "20261019"])
        self.assertEqual(list(result["departure_seconds"]), [30 * 60, 24 * 3600 + 30 * 60])

    def test_limit(self):
        trips, stop_times = _timetable(*[
            _trip(f"t{i}", "DAILY", "1", "Gamma", [("A1", f"09:{i:02d}:00"), ("C1", f"09:{i + 10:02d}:00")])
            for i in range(10, 20)
        ])
        self.assertEqual(len(_departures(trips, stop_times, "2026-10-19 09:00", limit=3)), 3)


class LiveOnlyDeparturesTest(unittest.TestCase):
    TODAY = pd.Timestamp("2026-10-19", tz="Australia/Sydney")

    def _rows(self, trip_id, calls):
        # calls: (stop_id, seq, scheduled clock time, delay seconds); times as the feed sends them.
        rows = []
        for stop, seq, hhmm, delay in calls:
            when = (pd.Timestamp(f"2026-10-19 {hhmm}", tz="Australia/Sydney") + pd.Timedelta(seconds=delay)).timestamp()
            rows.append({"trip_id": trip_id, "start_date": "20261019", "stop_id": stop, "stop_sequence": seq,
                         "arrival_time": when, "departure_time": when, "arrival_delay": delay})
        return pd.DataFrame(rows)

    def _departures(self, rows, from_station="Alpha Station", to_station="Gamma Station"):
        return live_only_departures(rows, _STOPS, from_station, to_station, self.TODAY)

    def test_schedule_is_feed_time_minus_delay(self):
        rows = self._rows("M1-X", [("A1", 1, "09:00", 120), ("B1", 2, "09:05", 120), ("C1", 3, "09:10", 60)])
        result = self._departures(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.loc[0, "departure_seconds"], 9 * 3600)
        self.assertEqual(result.loc[0, "arrival_seconds"], 9 * 3600 + 10 * 60)
        self.assertEqual(result.loc[0, "origin_stop_sequence"], 1)
        self.assertEqual(result.loc[0, "service_date"], "20261019")

    def test_destination_is_last_listed_station(self):
        rows = self._rows("M1-X", [("A1", 1, "09:00", 0), ("B1", 2, "09:05", 0), ("C1", 3, "09:10", 0)])
        self.assertEqual(self._departures(rows, to_station="Beta Station").loc[0, "trip_headsign"], "Gamma")

    def test_wrong_direction_excluded(self):
        rows = self._rows("M1-Y", [("C2", 1, "09:00", 0), ("B2", 2, "09:05", 0), ("A2", 3, "09:10", 0)])
        self.assertTrue(self._departures(rows).empty)

    def test_missing_arrival_at_first_stop_uses_departure(self):
        rows = self._rows("M1-X", [("A1", 1, "09:00", 0), ("C1", 2, "09:10", 0)])
        rows.loc[0, "arrival_time"] = 0  # the feed gives no arrival at a train's first stop
        self.assertEqual(self._departures(rows).loc[0, "departure_seconds"], 9 * 3600)

    def test_no_rows(self):
        self.assertTrue(self._departures(pd.DataFrame()).empty)


class FormattingTest(unittest.TestCase):
    def test_clock_wraps_past_midnight(self):
        self.assertEqual(clock(9 * 3600 + 5 * 60), "09:05")
        self.assertEqual(clock(24 * 3600 + 30 * 60), "00:30")
        self.assertEqual(clock(-30 * 60), "23:30")

    def test_nearest_horizon(self):
        self.assertEqual(nearest_horizon(0), 5)
        self.assertEqual(nearest_horizon(8), 10)
        self.assertEqual(nearest_horizon(40), 15)


if __name__ == "__main__":
    unittest.main()
