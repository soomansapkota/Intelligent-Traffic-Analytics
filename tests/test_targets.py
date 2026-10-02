import math
import unittest

import pandas as pd

from src.processing.targets import add_trip_targets, trip_delay_by_window


def _ts(hhmm):
    return pd.Timestamp(f"2026-08-15T{hhmm}:00Z")


def _trip_windows():
    return pd.DataFrame([
        {"route_id": "SMNW_M1", "trip_id": "T", "window_start": _ts("09:31"), "arrival_delay": 10.0},
        {"route_id": "SMNW_M1", "trip_id": "T", "window_start": _ts("09:36"), "arrival_delay": 25.0},
        {"route_id": "SMNW_M1", "trip_id": "T", "window_start": _ts("09:41"), "arrival_delay": 30.0},
        {"route_id": "SMNW_M1", "trip_id": "U", "window_start": _ts("09:36"), "arrival_delay": 99.0},
    ])


def _trip_delays():
    return pd.DataFrame([
        {"fetched_at": "2026-08-15T09:31:05+00:00", "trip_id": "T", "route_id": "SMNW_M1", "start_date": "20260815",
         "stop_id": "S3", "arrival_delay": 10, "stop_sequence": 3, "secs_to_arrival": -60, "is_passed": True},
        {"fetched_at": "2026-08-15T09:31:40+00:00", "trip_id": "T", "route_id": "SMNW_M1", "start_date": "20260815",
         "stop_id": "S4", "arrival_delay": 20, "stop_sequence": 4, "secs_to_arrival": -20, "is_passed": True},
        {"fetched_at": "2026-08-15T09:31:40+00:00", "trip_id": "V", "route_id": "SMNW_M1", "start_date": "20260815",
         "stop_id": "S2", "arrival_delay": 0, "stop_sequence": 2, "secs_to_arrival": 400, "is_passed": False},
    ])


class TripDelayByWindowTest(unittest.TestCase):
    def test_polls_in_same_minute_are_combined(self):
        result = trip_delay_by_window(_trip_delays()).set_index("trip_id")
        self.assertEqual(result.loc["T", "arrival_delay"], 15)
        self.assertEqual(result.loc["T", "stop_sequence"], 4)
        self.assertEqual(result.loc["T", "window_start"], _ts("09:31"))

    def test_keeps_service_day_and_freshest_stop(self):
        result = trip_delay_by_window(_trip_delays()).set_index("trip_id")
        self.assertEqual(result.loc["T", "start_date"], "20260815")
        self.assertEqual(result.loc["T", "stop_id"], "S4")

    def test_staleness_is_of_freshest_observation(self):
        result = trip_delay_by_window(_trip_delays()).set_index("trip_id")
        self.assertEqual(result.loc["T", "secs_since_stop"], 20)

    def test_measured_only_drops_undeparted_trips(self):
        result = trip_delay_by_window(_trip_delays())
        self.assertNotIn("V", result["trip_id"].tolist())

    def test_undeparted_trips_kept_when_measured_only_off(self):
        result = trip_delay_by_window(_trip_delays(), measured_only=False)
        self.assertIn("V", result["trip_id"].tolist())


class AddTripTargetsTest(unittest.TestCase):
    def setUp(self):
        out = add_trip_targets(_trip_windows(), horizons_minutes=(5, 10))
        self.result = out.set_index(["trip_id", "window_start"])

    def test_reads_same_trip_forward_by_horizon(self):
        row = self.result.loc[("T", _ts("09:31"))]
        self.assertEqual(row["target_delay_5min"], 25)
        self.assertEqual(row["target_delay_10min"], 30)

    def test_null_when_trip_not_observed_at_horizon(self):
        row = self.result.loc[("T", _ts("09:36"))]
        self.assertEqual(row["target_delay_5min"], 30)
        self.assertTrue(math.isnan(row["target_delay_10min"]))

    def test_never_borrows_another_trip(self):
        row = self.result.loc[("U", _ts("09:36"))]
        self.assertTrue(math.isnan(row["target_delay_5min"]))
        self.assertTrue(math.isnan(row["target_delay_10min"]))

    def test_last_observation_has_no_targets(self):
        row = self.result.loc[("T", _ts("09:41"))]
        self.assertTrue(math.isnan(row["target_delay_5min"]))
        self.assertTrue(math.isnan(row["target_delay_10min"]))

    def test_row_count_unchanged(self):
        self.assertEqual(len(self.result), 4)


if __name__ == "__main__":
    unittest.main()
