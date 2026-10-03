import unittest

import pandas as pd

from src.modeling.train import (
    MODELS,
    build_xy,
    chronological_split,
    regression_metrics,
    select_feature_columns,
    train_all,
    train_horizon_model,
)

HORIZONS = (5, 10, 15)


def _synthetic_dataset(n: int = 60) -> pd.DataFrame:
    """One trip, one row per minute, with the same column shape as model_dataset.

    arrival_delay ramps up over time so later windows are, on average,
    later-running than earlier ones -- a signal a model has something to
    learn from, unlike pure noise. Targets are built by shifting rows
    backwards by the horizon, which is exactly what a 1-minute-apart,
    single-trip series' time-based shift in targets.add_trip_targets
    reduces to.
    """
    window_start = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
    arrival_delay = pd.Series([float(i * 5 + (i % 3) * 7) for i in range(n)])

    df = pd.DataFrame({
        "trip_id": "T1",
        "route_id": "R1",
        "window_start": window_start,
        "start_date": "20260101",
        "stop_id": "S1",
        "arrival_delay": arrival_delay,
        "stop_sequence": 3,
        "secs_since_stop": 30,
        "lag_delay_1min": arrival_delay.shift(1),
        "hour": window_start.hour,
        "is_weekend": False,
        "is_peak": False,
        "net_mean_delay": arrival_delay * 0.8,
        # Identifier/text columns select_feature_columns must exclude.
        "static_trip_id": "ST1",
        "match_method": "exact",
        "trip_headsign": "City",
        "stop_name": "Central",
        "service_id": "WD",
    })
    for horizon in HORIZONS:
        df[f"target_delay_{horizon}min"] = arrival_delay.shift(-horizon)
    return df


class SelectFeatureColumnsTest(unittest.TestCase):
    def test_excludes_identifiers_and_every_target_column(self):
        columns = select_feature_columns(_synthetic_dataset())
        for excluded in ("trip_id", "route_id", "window_start", "start_date", "stop_id", "static_trip_id", "match_method", "trip_headsign", "stop_name", "service_id"):
            self.assertNotIn(excluded, columns)
        for horizon in HORIZONS:
            self.assertNotIn(f"target_delay_{horizon}min", columns)

    def test_keeps_numeric_and_boolean_features(self):
        columns = select_feature_columns(_synthetic_dataset())
        for kept in ("arrival_delay", "lag_delay_1min", "hour", "is_weekend", "net_mean_delay"):
            self.assertIn(kept, columns)


class ChronologicalSplitTest(unittest.TestCase):
    def test_train_rows_all_precede_test_rows(self):
        df = _synthetic_dataset()
        train_df, test_df = chronological_split(df, test_frac=0.2)
        self.assertEqual(len(train_df) + len(test_df), len(df))
        self.assertLessEqual(train_df["window_start"].max(), test_df["window_start"].min())

    def test_test_frac_controls_split_size(self):
        df = _synthetic_dataset(100)
        train_df, test_df = chronological_split(df, test_frac=0.3)
        self.assertEqual(len(test_df), 30)
        self.assertEqual(len(train_df), 70)


class BuildXyTest(unittest.TestCase):
    def test_drops_rows_with_null_target(self):
        df = _synthetic_dataset()
        columns = select_feature_columns(df)
        x, y = build_xy(df, horizon=5, feature_columns=columns)
        self.assertEqual(len(x), len(y))
        self.assertTrue(y.notna().all())
        self.assertEqual(len(x), len(df) - 5)  # last 5 rows have no target 5 minutes out

    def test_x_has_exactly_the_requested_columns(self):
        df = _synthetic_dataset()
        x, _ = build_xy(df, horizon=10, feature_columns=["arrival_delay", "hour"])
        self.assertEqual(list(x.columns), ["arrival_delay", "hour"])


class RegressionMetricsTest(unittest.TestCase):
    def test_perfect_predictions_score_zero_error_and_r2_one(self):
        y = pd.Series([1.0, 2.0, 3.0, 4.0])
        metrics = regression_metrics(y, y)
        self.assertAlmostEqual(metrics["mae"], 0.0)
        self.assertAlmostEqual(metrics["rmse"], 0.0)
        self.assertAlmostEqual(metrics["r2"], 1.0)


class TrainHorizonModelTest(unittest.TestCase):
    def test_reports_both_model_and_baseline_metrics(self):
        df = _synthetic_dataset()
        columns = select_feature_columns(df)
        train_df, test_df = chronological_split(df, test_frac=0.3)
        model, report = train_horizon_model(train_df, test_df, horizon=5, feature_columns=columns)
        self.assertIsNotNone(model)
        for key in ("mae", "rmse", "r2"):
            self.assertIn(key, report["model_metrics"])
            self.assertIn(key, report["baseline_metrics"])
        self.assertGreaterEqual(report["model_metrics"]["mae"], 0.0)
        self.assertEqual(report["n_train"] + report["n_test"], len(df) - 5)

    def test_returns_no_model_when_a_split_has_no_labelled_rows(self):
        # A 15-row frame with a 2-row test split leaves the test half
        # entirely inside the last 5 rows, which have no 5-minute-out target.
        df = _synthetic_dataset(15)
        columns = select_feature_columns(df)
        train_df, test_df = chronological_split(df, test_frac=0.13)
        model, report = train_horizon_model(train_df, test_df, horizon=5, feature_columns=columns)
        self.assertIsNone(model)
        self.assertEqual(report["n_test"], 0)
        self.assertNotIn("model_metrics", report)


class TrainAllTest(unittest.TestCase):
    def test_trains_one_model_per_horizon(self):
        df = _synthetic_dataset(80)
        models, reports, feature_columns = train_all(df, horizons=HORIZONS, test_frac=0.25)
        self.assertEqual(set(models.keys()), set(HORIZONS))
        self.assertEqual(set(reports.keys()), set(HORIZONS))
        self.assertTrue(len(feature_columns) > 0)

    def test_every_model_type_trains_and_is_recorded_in_the_report(self):
        df = _synthetic_dataset(80)
        df.loc[::4, "lag_delay_1min"] = None  # models must cope with missing features
        for model_name in MODELS:
            with self.subTest(model=model_name):
                models, reports, _ = train_all(df, horizons=(5,), test_frac=0.25, model_name=model_name)
                self.assertIn(5, models)
                self.assertEqual(reports[5]["model"], model_name)
                self.assertIn("model_metrics", reports[5])


if __name__ == "__main__":
    unittest.main()
