import math
import unittest

import pandas as pd

from src.processing.features import (
    add_lag_features,
    add_network_features,
    add_rolling_features,
    add_temporal_features,
)


def _ts(iso):
    return pd.Timestamp(iso)


def _trip_windows():
    return pd.DataFrame([
        {"route_id": "SMNW_M1", "trip_id": "T", "window_start": _ts("2026-08-15T09:31:00Z"), "arrival_delay": 10.0},
        {"route_id": "SMNW_M1", "trip_id": "T", "window_start": _ts("2026-08-15T09:36:00Z"), "arrival_delay": 25.0},
        {"route_id": "SMNW_M1", "trip_id": "T", "window_start": _ts("2026-08-15T09:37:00Z"), "arrival_delay": 28.0},
        {"route_id": "SMNW_M1", "trip_id": "T", "window_start": _ts("2026-08-15T09:41:00Z"), "arrival_delay": 30.0},
        {"route_id": "SMNW_M1", "trip_id": "U", "window_start": _ts("2026-08-15T09:36:00Z"), "arrival_delay": 99.0},
    ])


class LagFeaturesTest(unittest.TestCase):
    def setUp(self):
        self.result = add_lag_features(_trip_windows()).set_index(["trip_id", "window_start"])

    def test_lag_reads_same_trip_backwards(self):
        self.assertEqual(self.result.loc[("T", _ts("2026-08-15T09:36:00Z")), "lag_delay_5min"], 10)
        self.assertEqual(self.result.loc[("T", _ts("2026-08-15T09:41:00Z")), "lag_delay_5min"], 25)

    def test_lag_null_when_not_observed(self):
        self.assertTrue(math.isnan(self.result.loc[("T", _ts("2026-08-15T09:31:00Z")), "lag_delay_5min"]))
        self.assertTrue(math.isnan(self.result.loc[("U", _ts("2026-08-15T09:36:00Z")), "lag_delay_5min"]))

    def test_delay_change_uses_one_minute_lag(self):
        row = self.result.loc[("T", _ts("2026-08-15T09:37:00Z"))]
        self.assertEqual(row["lag_delay_1min"], 25)
        self.assertEqual(row["delay_change_1min"], 3)
        self.assertTrue(math.isnan(self.result.loc[("T", _ts("2026-08-15T09:36:00Z")), "delay_change_1min"]))


class RollingFeaturesTest(unittest.TestCase):
    def setUp(self):
        self.source = _trip_windows()
        self.result = add_rolling_features(self.source, windows_minutes=(15,))

    def test_trailing_window_includes_prior_observations(self):
        row = self.result.set_index(["trip_id", "window_start"]).loc[("T", _ts("2026-08-15T09:41:00Z"))]
        self.assertAlmostEqual(row["rolling_mean_15min"], (10 + 25 + 28 + 30) / 4)
        self.assertEqual(row["rolling_max_15min"], 30)
        self.assertEqual(row["n_obs_15min"], 4)

    def test_first_observation_only_sees_itself(self):
        row = self.result.set_index(["trip_id", "window_start"]).loc[("T", _ts("2026-08-15T09:31:00Z"))]
        self.assertEqual(row["rolling_mean_15min"], 10)
        self.assertEqual(row["n_obs_15min"], 1)

    def test_no_leakage_between_trips(self):
        row = self.result.set_index(["trip_id", "window_start"]).loc[("U", _ts("2026-08-15T09:36:00Z"))]
        self.assertEqual(row["rolling_mean_15min"], 99)
        self.assertEqual(row["n_obs_15min"], 1)

    def test_original_row_order_preserved(self):
        self.assertListEqual(self.result.index.tolist(), self.source.index.tolist())
        self.assertListEqual(self.result["trip_id"].tolist(), self.source["trip_id"].tolist())


class TemporalFeaturesTest(unittest.TestCase):
    def _row(self, iso):
        df = pd.DataFrame({"window_start": [_ts(iso)]})
        return add_temporal_features(df).iloc[0]

    def test_converts_to_sydney_local_time(self):
        row = self._row("2026-08-15T09:31:00Z")
        self.assertEqual(row["hour"], 19)
        self.assertEqual(row["day_of_week"], 5)
        self.assertTrue(row["is_weekend"])
        self.assertFalse(row["is_peak"])

    def test_weekday_morning_peak(self):
        row = self._row("2026-08-16T22:30:00Z")
        self.assertEqual(row["hour"], 8)
        self.assertEqual(row["day_of_week"], 0)
        self.assertFalse(row["is_weekend"])
        self.assertTrue(row["is_peak"])

    def test_weekday_evening_peak(self):
        self.assertTrue(self._row("2026-08-17T07:00:00Z")["is_peak"])

    def test_weekday_midday_not_peak(self):
        self.assertFalse(self._row("2026-08-17T02:00:00Z")["is_peak"])


class NetworkFeaturesTest(unittest.TestCase):
    def test_route_aggregates_joined_with_prefix(self):
        windows = pd.DataFrame([
            {"route_id": "SMNW_M1", "window_start": _ts("2026-08-15T09:31:00Z"), "mean_delay": 7.0, "n_trips": 40},
        ])
        result = add_network_features(_trip_windows(), windows).set_index(["trip_id", "window_start"])
        self.assertEqual(result.loc[("T", _ts("2026-08-15T09:31:00Z")), "net_mean_delay"], 7)
        self.assertEqual(result.loc[("T", _ts("2026-08-15T09:31:00Z")), "net_n_trips"], 40)
        self.assertTrue(math.isnan(result.loc[("T", _ts("2026-08-15T09:36:00Z")), "net_mean_delay"]))


if __name__ == "__main__":
    unittest.main()
