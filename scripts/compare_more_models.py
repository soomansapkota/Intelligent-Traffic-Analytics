"""Compare XGBoost, LightGBM and a tuned hgb_change_abs against the current best.

Uses exactly the evaluation of notebooks/model_comparison.ipynb -- the same
impossible-delay filter, the same four rolling time folds and the same guard
that drops training rows whose target would look into the test block -- so
the numbers line up with the notebook's table. Persistence and the default
hgb_change_abs are re-run alongside as reference points.

Every new model goes through PredictChange with an absolute-error loss,
since that combination is what made hgb_change_abs the only model to beat
persistence.

Tuning never looks at a test fold: within each fold, the last 20% of the
training rows (by time) are held out to pick the parameters, then the
winner is refit on the whole training part and scored on the test block.

    python -m scripts.compare_more_models
"""

import argparse
import itertools
import logging
import pickle
import random
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from xgboost import XGBRegressor

from src.modeling.change import AsFloat, PredictChange
from src.modeling.train import build_xy, regression_metrics, select_feature_columns
from src.processing.targets import DEFAULT_HORIZONS_MINUTES
from src.storage.db import get_engine, read_table

logger = logging.getLogger(__name__)

HORIZONS = DEFAULT_HORIZONS_MINUTES
MAX_ABS_DELAY = 3600
N_FOLDS = 4
MIN_TRAIN, MIN_TEST = 50, 10
TUNE_VALID_FRAC = 0.2
TUNE_TRIALS = 12
WITHIN_SECONDS = 30
N_JOBS = 4  # leaves cores free, as in the notebook


class Persistence:
    """Predicts that the delay later equals the delay now."""

    def fit(self, X, y):
        return self

    def predict(self, X):
        return X["arrival_delay"].to_numpy()


def hgb_abs(**params):
    return HistGradientBoostingRegressor(loss="absolute_error", random_state=42, **params)


MODELS = {
    "persistence": lambda: Persistence(),
    "hgb_change_abs": lambda: PredictChange(hgb_abs()),
    "xgboost_change_abs": lambda: PredictChange(AsFloat(XGBRegressor(
        objective="reg:absoluteerror", n_estimators=300, learning_rate=0.1, max_depth=6,
        tree_method="hist", n_jobs=N_JOBS, random_state=42,
    ))),
    "lightgbm_change_abs": lambda: PredictChange(AsFloat(LGBMRegressor(
        objective="l1", n_estimators=300, learning_rate=0.1, num_leaves=31,
        n_jobs=N_JOBS, random_state=42, verbose=-1,
    ))),
}

# Search space for hgb_change_abs. TUNE_TRIALS combinations are sampled
# (fixed seed) and the default settings are always included as a candidate,
# so tuning can never pick something worse on validation than the default.
HGB_GRID = {
    "learning_rate": [0.03, 0.05, 0.1, 0.2],
    "max_iter": [200, 400],
    "max_leaf_nodes": [15, 31, 63],
    "min_samples_leaf": [20, 50, 200],
    "l2_regularization": [0.0, 1.0],
}
HGB_DEFAULT = {"learning_rate": 0.1, "max_iter": 100, "max_leaf_nodes": 31, "min_samples_leaf": 20, "l2_regularization": 0.0}


def load_dataset() -> tuple[pd.DataFrame, list[str]]:
    engine = get_engine()
    df = read_table(engine, "model_dataset")
    engine.dispose()

    df["window_start"] = pd.to_datetime(df["window_start"], utc=True)
    df = df.sort_values("window_start").reset_index(drop=True)
    features = select_feature_columns(df)

    delay_cols = ["arrival_delay"] + [f"target_delay_{h}min" for h in HORIZONS]
    bad = (df[delay_cols].abs() > MAX_ABS_DELAY).any(axis=1)
    logger.info(f"dropping {int(bad.sum())} impossible-delay rows of {len(df)}")
    return df[~bad].reset_index(drop=True), features


def time_folds(df: pd.DataFrame, n_folds: int = N_FOLDS):
    """Rolling-origin folds cut on unique timestamps, as in the notebook."""
    times = np.sort(df["window_start"].unique())
    edges = [times[int(len(times) * k / (n_folds + 1))] for k in range(1, n_folds + 1)] + [None]
    for k in range(n_folds):
        test_start, test_end = edges[k], edges[k + 1]
        test_mask = df["window_start"] >= test_start
        if test_end is not None:
            test_mask &= df["window_start"] < test_end
        yield k, df["window_start"] < test_start, test_mask


def safe_before(df: pd.DataFrame, mask: pd.Series, cutoff, horizon: int) -> pd.Series:
    """Rows in mask whose target is observed before cutoff."""
    return mask & (df["window_start"] + pd.Timedelta(minutes=horizon) < cutoff)


def tune_hgb(df, features, train_mask, horizon) -> dict:
    """Pick hgb_change_abs parameters on a time-ordered slice of the training rows."""
    train_times = np.sort(df.loc[train_mask, "window_start"].unique())
    valid_start = train_times[int(len(train_times) * (1 - TUNE_VALID_FRAC))]
    valid_mask = train_mask & (df["window_start"] >= valid_start)
    x_fit, y_fit = build_xy(df[safe_before(df, train_mask, valid_start, horizon)], horizon, features)
    x_val, y_val = build_xy(df[valid_mask], horizon, features)
    if len(x_fit) < MIN_TRAIN or len(x_val) < MIN_TEST:
        return HGB_DEFAULT

    combos = [dict(zip(HGB_GRID, values)) for values in itertools.product(*HGB_GRID.values())]
    candidates = [HGB_DEFAULT] + random.Random(42).sample(combos, TUNE_TRIALS)
    scored = []
    for params in candidates:
        pred = PredictChange(hgb_abs(**params)).fit(x_fit, y_fit).predict(x_val)
        scored.append((float(np.mean(np.abs(y_val - pred))), params))
    return min(scored, key=lambda t: t[0])[1]


def evaluate(df: pd.DataFrame, features: list[str]) -> tuple[pd.DataFrame, list[dict]]:
    rows, chosen = [], []
    for horizon in HORIZONS:
        for k, train_mask, test_mask in time_folds(df):
            test_start = df.loc[test_mask, "window_start"].min()
            safe_train = safe_before(df, train_mask, test_start, horizon)
            x_train, y_train = build_xy(df[safe_train], horizon, features)
            x_test, y_test = build_xy(df[test_mask], horizon, features)
            if len(x_train) < MIN_TRAIN or len(x_test) < MIN_TEST:
                continue

            builders = dict(MODELS)
            started = time.perf_counter()
            params = tune_hgb(df, features, safe_train, horizon)
            tune_seconds = time.perf_counter() - started
            chosen.append({"horizon": horizon, "fold": k, **params})
            builders["hgb_change_abs_tuned"] = lambda params=params: PredictChange(hgb_abs(**params))

            for name, build in builders.items():
                started = time.perf_counter()
                model = build().fit(x_train, y_train)
                fit_seconds = time.perf_counter() - started
                started = time.perf_counter()
                pred = model.predict(x_test)
                predict_seconds = time.perf_counter() - started
                rows.append({
                    "horizon": horizon, "fold": k, "model": name,
                    "n_train": len(x_train), "n_test": len(x_test),
                    **regression_metrics(y_test, pred),
                    "within_30s": float(np.mean(np.abs(y_test - pred) <= WITHIN_SECONDS)),
                    "fit_seconds": fit_seconds + (tune_seconds if name == "hgb_change_abs_tuned" else 0.0),
                    "predict_seconds": predict_seconds,
                    "size_mb": len(pickle.dumps(model)) / 1e6,
                })
                logger.info(f"{horizon} min, fold {k}, {name}: MAE {rows[-1]['mae']:.2f}")
    return pd.DataFrame(rows), chosen


def plot(results: pd.DataFrame, out: Path) -> None:
    order = results.pivot_table(index="model", columns="horizon", values="mae").sort_values(HORIZONS[-1]).index
    fig, ax = plt.subplots(figsize=(8, 4.5))
    width = 0.8 / len(order)
    for i, name in enumerate(order):
        stats = results[results["model"] == name].groupby("horizon")["mae"].agg(["mean", "std"])
        x = np.arange(len(HORIZONS)) + (i - (len(order) - 1) / 2) * width
        ax.bar(x, stats["mean"], width, yerr=stats["std"], capsize=2, label=name)
    ax.set_xticks(np.arange(len(HORIZONS)), [f"{h} min" for h in HORIZONS])
    ax.set_ylabel("MAE (seconds), mean across folds")
    ax.set_title("Delay prediction error by horizon (lower is better)")
    ax.legend(fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare XGBoost, LightGBM and tuned HGB on the notebook's time folds")
    parser.add_argument("--out-dir", type=Path, default=Path("Assessment Reports"), help="Where to write the CSVs and chart")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    df, features = load_dataset()
    logger.info(f"{len(df)} rows, {df['trip_id'].nunique()} trains, {len(features)} features")
    results, chosen = evaluate(df, features)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    results.to_csv(args.out_dir / "more_models_results.csv", index=False)
    pd.DataFrame(chosen).to_csv(args.out_dir / "hgb_tuned_params.csv", index=False)
    plot(results, args.out_dir / "more_models_comparison.png")

    pd.set_option("display.width", 200)
    print("\nMAE (s), mean across folds")
    print(results.pivot_table(index="model", columns="horizon", values="mae").round(2).sort_values(HORIZONS[-1]))
    print("\nShare of predictions within 30 s")
    print(results.pivot_table(index="model", columns="horizon", values="within_30s").round(3))
    base = results[results["model"] == "persistence"].set_index(["horizon", "fold"])["mae"]
    gain = results[results["model"] != "persistence"].copy()
    gain["gain"] = 1 - gain["mae"] / gain.set_index(["horizon", "fold"]).index.map(base)
    print("\nGain over persistence (above 0 = better)")
    print(gain.pivot_table(index="model", columns="horizon", values="gain").round(3))
    print("\nCost, mean per fit")
    print(results.groupby("model")[["fit_seconds", "predict_seconds", "size_mb"]].mean().round(3))
    print("\nTuned parameters chosen per fold")
    print(pd.DataFrame(chosen).to_string(index=False))


if __name__ == "__main__":
    main()
