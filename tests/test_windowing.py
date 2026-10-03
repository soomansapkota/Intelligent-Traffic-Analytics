import unittest

import pandas as pd

from src.processing.windowing import build_windows, current_trip_delay

FETCHED_AT = "2026-08-15T09:31:00+00:00"
NOW = int(pd.Timestamp(FETCHED_AT).timestamp())


def _stop(trip_id, stop_sequence, offset_seconds, delay):
    return {
        "entity_id": trip_id,
        "trip_id": trip_id,
        "route_id": "SMNW_M1",
        "start_date": "20260815",
        "stop_sequence": stop_sequence,
        "stop_id": f"stop{stop_sequence}",
        "arrival_time": 0 if offset_seconds is None else NOW + offset_seconds,
        "arrival_delay": delay,
        "departure_time": 0,
        "schedule_relationship": "SCHEDULED",
        "fetched_at": FETCHED_AT,
    }


def _trip_updates():
    return pd.DataFrame([
        _stop("A", 1, None, 0),
        _stop("A", 2, -300, 10),
        _stop("A", 3, -60, 20),
        _stop("A", 4, 120, 5),
        _stop("B", 1, None, 0),
        _stop("B", 2, 60, 0),
        _stop("B", 3, 300, 3),
    ])


def _vehicle_positions():
    return pd.DataFrame([
        {"route_id": "SMNW_M1", "vehicle_id": "V1", "speed": 0.0, "current_status": "STOPPED_AT", "fetched_at": FETCHED_AT},
        {"route_id": "SMNW_M1", "vehicle_id": "V2", "speed": 20.0, "current_status": "IN_TRANSIT_TO", "fetched_at": FETCHED_AT},
    ])


class CurrentTripDelayTest(unittest.TestCase):
    def test_keeps_most_recently_passed_stop(self):
        result = current_trip_delay(_trip_updates()).set_index("trip_id")
        self.assertEqual(result.loc["A", "stop_sequence"], 3)
        self.assertEqual(result.loc["A", "arrival_delay"], 20)
        self.assertTrue(result.loc["A", "is_passed"])

    def test_falls_back_to_next_stop_when_none_passed(self):
        result = current_trip_delay(_trip_updates()).set_index("trip_id")
        self.assertEqual(result.loc["B", "stop_sequence"], 2)
        self.assertEqual(result.loc["B", "secs_to_arrival"], 60)
        self.assertFalse(result.loc["B", "is_passed"])

    def test_drops_rows_without_arrival_time(self):
        result = current_trip_delay(_trip_updates())
        self.assertEqual(len(result), 2)
        self.assertTrue((result["arrival_time"] > 0).all())

    def test_empty_input_returns_empty(self):
        result = current_trip_delay(_trip_updates().iloc[0:0])
        self.assertTrue(result.empty)


class BuildWindowsTest(unittest.TestCase):
    def test_measured_only_excludes_undeparted_trips(self):
        delays = current_trip_delay(_trip_updates())
        windows = build_windows(delays, _vehicle_positions())
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows.loc[0, "n_trips"], 1)
        self.assertEqual(windows.loc[0, "mean_delay"], 20)

    def test_all_trips_when_measured_only_off(self):
        delays = current_trip_delay(_trip_updates())
        windows = build_windows(delays, _vehicle_positions(), measured_only=False)
        self.assertEqual(windows.loc[0, "n_trips"], 2)
        self.assertEqual(windows.loc[0, "mean_delay"], 10)

    def test_vehicle_aggregates(self):
        delays = current_trip_delay(_trip_updates())
        windows = build_windows(delays, _vehicle_positions())
        self.assertEqual(windows.loc[0, "n_vehicles"], 2)
        self.assertEqual(windows.loc[0, "mean_speed"], 10)
        self.assertEqual(windows.loc[0, "frac_stopped"], 0.5)

    def test_window_start_is_floored_to_minute(self):
        delays = current_trip_delay(_trip_updates())
        windows = build_windows(delays, _vehicle_positions())
        self.assertEqual(windows.loc[0, "window_start"], pd.Timestamp("2026-08-15T09:31:00Z"))


if __name__ == "__main__":
    unittest.main()
