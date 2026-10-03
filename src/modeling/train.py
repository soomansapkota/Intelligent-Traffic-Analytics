"""Train and evaluate delay-prediction models on model_dataset.

One regressor is trained per horizon (5/10/15 min, matching the target
columns src.processing.targets attaches), each scored against a persistence
baseline -- "the delay a horizon from now equals the delay right now" -- so
a model's numbers mean something: beating a naive guess, not just being
non-random.

Run as a script to train from the database and save the results:

    python -m src.modeling.train

Pick the model type with --model (see MODELS); save each type to its own
directory so their models and metrics can be compared side by side:

    python -m src.modeling.train --model random_forest --out-dir models/random_forest

Usage as a library keeps the pieces independently testable: select_feature_columns,
chronological_split, build_xy, train_horizon_model, train_all.
"""

import argparse
import json
import logging
from pathlib import Path

import joblib
import pandas as pd
from sklearn.base import RegressorMixin
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from src.modeling.change import PredictChange
from src.processing.targets import DEFAULT_HORIZONS_MINUTES
from src.storage.db import get_engine, read_table

logger = logging.getLogger(__name__)

# Columns that identify a row rather than describe it. Excluded even though
# a couple (direction_id aside) are never numeric anyway, so this is a
# safety net rather than the main filter -- see select_feature_columns.
ID_COLUMNS = {
    "trip_id", "route_id", "window_start", "start_date", "stop_id",
    "static_trip_id", "match_method", "trip_headsign", "stop_name", "service_id",
}

# Model types --model can pick from. All of them handle NaN features natively
# (random forests since scikit-learn 1.4), so build_xy needs no imputation
# whichever is chosen. The forest is capped in depth and leaf size so it
# trains in minutes on a full model_dataset rather than growing every tree
# out to single rows.
MODELS = {
    "hist_gradient_boosting": lambda: HistGradientBoostingRegressor(random_state=42),
    "random_forest": lambda: RandomForestRegressor(
        n_estimators=100, max_depth=20, min_samples_leaf=5, n_jobs=-1, random_state=42
    ),
    "hgb_change_abs": lambda: PredictChange(HistGradientBoostingRegressor(loss="absolute_error", random_state=42)),
}
DEFAULT_MODEL = "hgb_change_abs"


def select_feature_columns(df: pd.DataFrame) -> list[str]:
    """Pick the numeric columns usable as model input.

    Every target_delay_<h>min column is excluded regardless of horizon, so
    a model for one horizon never sees another horizon's label. New
    engineered features are picked up automatically as long as they are
    numeric, rather than needing to be hand-listed here.

    Args:
        df: model_dataset, or any frame with the same column set.

    Returns:
        Feature column names, in df's column order.
    """
    numeric = df.select_dtypes(include=["number", "bool"]).columns
    return [c for c in numeric if c not in ID_COLUMNS and not c.startswith("target_delay_")]


def chronological_split(df: pd.DataFrame, test_frac: float = 0.2) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split rows by time rather than randomly.

    A random split would let a model trained on one trip's 10:05 window
    see that same trip's 10:04 window at test time -- barely a fair test,
    since rolling/lag features make adjacent windows highly similar. A
    chronological split holds out only the latest slice of time, closer to
    how the model is actually used: predicting a future it has not seen.

    Args:
        df: model_dataset, or any frame with a window_start column.
        test_frac: Fraction of rows, by time, held out for testing.

    Returns:
        (train_df, test_df), both sorted by window_start.
    """
    ordered = df.sort_values("window_start")
    cutoff = int(len(ordered) * (1 - test_frac))
    return ordered.iloc[:cutoff], ordered.iloc[cutoff:]


def build_xy(df: pd.DataFrame, horizon: int, feature_columns: list[str]) -> tuple[pd.DataFrame, pd.Series]:
    """Select features and the target for one horizon, dropping unlabelled rows.

    Missing feature values (e.g. a lag with no prior observation) are left
    as NaN rather than filled: every model in MODELS handles them
    natively, and filling with 0 would misrepresent "unknown" as "on time".

    Args:
        df: model_dataset, or any frame with the same column set.
        horizon: Horizon in minutes, selecting the target_delay_<h>min column.
        feature_columns: Columns to use as model input.

    Returns:
        (X, y) with matching indices, rows without a target dropped.
    """
    target_col = f"target_delay_{horizon}min"
    labelled = df.dropna(subset=[target_col])
    return labelled[feature_columns], labelled[target_col]


def regression_metrics(y_true: pd.Series, y_pred) -> dict[str, float]:
    """Compute the standard regression metrics for a set of predictions.

    Args:
        y_true: Observed values.
        y_pred: Predicted values, same order.

    Returns:
        Dict with mae, rmse and r2 (mean absolute/root-mean-squared error
        in the target's own units -- seconds of delay -- and the
        coefficient of determination).
    """
    return {
        "mae": mean_absolute_error(y_true, y_pred),
        "rmse": mean_squared_error(y_true, y_pred) ** 0.5,
        "r2": r2_score(y_true, y_pred),
    }


def train_horizon_model(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    horizon: int,
    feature_columns: list[str],
    model_name: str = DEFAULT_MODEL,
) -> tuple[RegressorMixin | None, dict]:
    """Train and evaluate one horizon's model against the persistence baseline.

    Args:
        train_df: Earlier rows, from chronological_split.
        test_df: Later rows, from chronological_split.
        horizon: Horizon in minutes.
        feature_columns: Columns to use as model input.
        model_name: Key into MODELS choosing the regressor type.

    Returns:
        (model, report). model is None when there is no labelled data to
        train or test on for this horizon; report always carries at least
        n_train/n_test so a caller can tell why.
    """
    x_train, y_train = build_xy(train_df, horizon, feature_columns)
    x_test, y_test = build_xy(test_df, horizon, feature_columns)

    report = {"horizon_minutes": horizon, "model": model_name, "n_train": len(x_train), "n_test": len(x_test)}
    if x_train.empty or x_test.empty:
        logger.warning(f"{horizon}min: not enough labelled rows to train/evaluate (train={len(x_train)}, test={len(x_test)})")
        return None, report

    model = MODELS[model_name]()
    model.fit(x_train, y_train)
    y_pred = model.predict(x_test)

    # The persistence baseline: guess that the delay a horizon from now is
    # today's delay. arrival_delay is aligned back onto the test rows that
    # survived build_xy's dropna, so both scores are computed on the same rows.
    baseline_pred = test_df.loc[x_test.index, "arrival_delay"]

    report["model_metrics"] = regression_metrics(y_test, y_pred)
    report["baseline_metrics"] = regression_metrics(y_test, baseline_pred)
    return model, report


def train_all(
    df: pd.DataFrame,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS_MINUTES,
    test_frac: float = 0.2,
    model_name: str = DEFAULT_MODEL,
) -> tuple[dict[int, RegressorMixin], dict[int, dict], list[str]]:
    """Train and evaluate one model per horizon.

    Args:
        df: model_dataset.
        horizons: Horizons in minutes to train for.
        test_frac: Fraction of rows, by time, held out for testing.
        model_name: Key into MODELS choosing the regressor type.

    Returns:
        (models, reports, feature_columns). models and reports are keyed by
        horizon; a horizon with no model (see train_horizon_model) is
        omitted from models but still present in reports.
    """
    feature_columns = select_feature_columns(df)
    train_df, test_df = chronological_split(df, test_frac)

    models, reports = {}, {}
    for horizon in horizons:
        model, report = train_horizon_model(train_df, test_df, horizon, feature_columns, model_name)
        reports[horizon] = report
        if model is not None:
            models[horizon] = model

    return models, reports, feature_columns


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train delay-prediction models from model_dataset")
    parser.add_argument("--out-dir", type=Path, default=Path("models"), help="Directory to save models and metrics into")
    parser.add_argument("--test-frac", type=float, default=0.2, help="Fraction of rows, by time, held out for testing")
    parser.add_argument("--model", choices=sorted(MODELS), default=DEFAULT_MODEL, help="Regressor type to train")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    engine = get_engine()
    df = read_table(engine, "model_dataset")
    engine.dispose()

    if df.empty:
        logger.warning("model_dataset is empty -- run `python -m src.orchestration.pipeline --build-dataset` first")
        return

    df["window_start"] = pd.to_datetime(df["window_start"], utc=True)
    models, reports, feature_columns = train_all(df, test_frac=args.test_frac, model_name=args.model)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for horizon, model in models.items():
        joblib.dump(model, args.out_dir / f"delay_model_{horizon}min.joblib")
    (args.out_dir / "feature_columns.json").write_text(json.dumps(feature_columns, indent=2))
    (args.out_dir / "metrics.json").write_text(json.dumps(reports, indent=2))

    for horizon, report in reports.items():
        if "model_metrics" not in report:
            continue
        m, b = report["model_metrics"], report["baseline_metrics"]
        logger.info(
            f"{horizon}min: {args.model} MAE={m['mae']:.1f}s RMSE={m['rmse']:.1f}s R2={m['r2']:.3f} "
            f"| baseline MAE={b['mae']:.1f}s RMSE={b['rmse']:.1f}s R2={b['r2']:.3f} "
            f"(n_train={report['n_train']}, n_test={report['n_test']})"
        )
    logger.info(f"saved {len(models)} model(s) and metrics to {args.out_dir}/")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
