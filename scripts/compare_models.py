"""Compare the trained delay models and plot accuracy against practical cost.

Scores the saved models in models/ (HistGradientBoosting) and
models/random_forest/ on the same chronological test split train.py uses,
alongside the persistence baseline, then times training and prediction and
measures model file size. Everything is computed from the database and the
saved models on each run, so the chart stays current after retraining.

    python -m scripts.compare_models
    python -m scripts.compare_models --out "Assessment Reports/model_comparison.png"

Training time is measured by refitting the 5-minute model once per type
(about a minute for the random forest); the saved models are not changed.
"""

import argparse
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.modeling.predict import load_feature_columns, load_model
from src.modeling.train import MODELS, build_xy, chronological_split, regression_metrics
from src.processing.targets import DEFAULT_HORIZONS_MINUTES
from src.storage.db import get_engine, read_table

# Model type -> directory train.py saved it into (see README / --out-dir).
MODEL_DIRS = {"random_forest": Path("models/random_forest"), "hist_gradient_boosting": Path("models")}
LABELS = {"random_forest": "Random Forest", "hist_gradient_boosting": "HistGradientBoosting", "baseline": "Baseline (delay stays the same)"}
# Colour-blind-safe categorical palette (validated): one fixed colour per model.
COLORS = {"random_forest": "#00897B", "hist_gradient_boosting": "#C96A0A", "baseline": "#5C6BC0"}
INK, MUTED, GRID = "#1B2B34", "#6B7C86", "#E3E8EA"


def evaluate(df: pd.DataFrame, test_frac: float) -> tuple[dict, dict]:
    """Score every model and the baseline per horizon, and measure cost.

    Returns:
        (accuracy, cost). accuracy[name][horizon] holds mae, rmse, r2 and
        pct_off_1min; cost[name] holds fit_seconds, predict_seconds, size_mb.
    """
    train_df, test_df = chronological_split(df, test_frac)
    accuracy = {name: {} for name in (*MODEL_DIRS, "baseline")}
    cost = {}

    for name, model_dir in MODEL_DIRS.items():
        columns = load_feature_columns(model_dir)
        for h in DEFAULT_HORIZONS_MINUTES:
            x_test, y_test = build_xy(test_df, h, columns)
            model = load_model(h, model_dir)
            start = time.perf_counter()
            pred = model.predict(x_test)
            if h == DEFAULT_HORIZONS_MINUTES[0]:
                cost[name] = {"predict_seconds": time.perf_counter() - start, "n_predict": len(x_test)}
            accuracy[name][h] = regression_metrics(y_test, pred) | {"pct_off_1min": float((np.abs(pred - y_test) > 60).mean() * 100)}
            if name == "hist_gradient_boosting":  # baseline needs the same rows; score it once
                base = test_df.loc[x_test.index, "arrival_delay"]
                accuracy["baseline"][h] = regression_metrics(y_test, base) | {"pct_off_1min": float(((base - y_test).abs() > 60).mean() * 100)}

        h = DEFAULT_HORIZONS_MINUTES[0]
        x_train, y_train = build_xy(train_df, h, columns)
        start = time.perf_counter()
        MODELS[name]().fit(x_train, y_train)
        cost[name]["fit_seconds"] = time.perf_counter() - start
        cost[name]["size_mb"] = sum((model_dir / f"delay_model_{h}min.joblib").stat().st_size for h in DEFAULT_HORIZONS_MINUTES) / 1e6

    return accuracy, cost


def plot(accuracy: dict, cost: dict, out: Path, test_desc: str) -> None:
    plt.rcParams.update({"font.family": ["Calibri", "DejaVu Sans"], "font.size": 11, "axes.edgecolor": GRID, "xtick.color": MUTED, "ytick.color": MUTED})
    fig, axes = plt.subplots(2, 3, figsize=(16, 9), dpi=200)

    def style(ax, title):
        ax.set_title(title, color=INK, fontsize=13, loc="left", pad=10)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.yaxis.grid(True, color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
        ax.tick_params(length=0)

    horizons = list(DEFAULT_HORIZONS_MINUTES)
    x, w = np.arange(len(horizons)), 0.26
    panels = [
        ("mae", "MAE (seconds) – lower is better", "{:.1f}"),
        ("r2", "R² – higher is better", "{:.2f}"),
        ("pct_off_1min", "Predictions off by more than 1 minute (%) – lower is better", "{:.1f}%"),
    ]
    for ax, (key, title, fmt) in zip(axes[0], panels):
        for offset, name in zip((-w, 0, w), ("random_forest", "hist_gradient_boosting", "baseline")):
            vals = [accuracy[name][h][key] for h in horizons]
            bars = ax.bar(x + offset, vals, w * 0.92, color=COLORS[name], label=LABELS[name])
            ax.bar_label(bars, labels=[fmt.format(v) for v in vals], padding=2, fontsize=9, color=INK)
        ax.set_xticks(x, [f"{h} min" for h in horizons])
        if key == "r2":
            ax.set_ylim(0, 1.05)
        style(ax, title)

    n_pred = cost["random_forest"]["n_predict"]
    cost_panels = [
        ("fit_seconds", f"Training time, {horizons[0]}-min model (seconds)", "{:.1f} s"),
        ("size_mb", "Model files on disk, all horizons (MB)", "{:.1f} MB"),
        ("predict_seconds", f"Prediction time, {n_pred:,} rows (seconds)", "{:.2f} s"),
    ]
    names = list(MODEL_DIRS)
    for ax, (key, title, fmt) in zip(axes[1], cost_panels):
        vals = [cost[n][key] for n in names]
        bars = ax.bar(range(len(names)), vals, 0.5, color=[COLORS[n] for n in names])
        ax.bar_label(bars, labels=[fmt.format(v) for v in vals], padding=3, fontsize=11, color=INK)
        ax.set_xticks(range(len(names)), [LABELS[n] for n in names])
        ax.set_ylim(0, max(vals) * 1.18)
        style(ax, title + " – lower is better")

    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, frameon=False, fontsize=12, bbox_to_anchor=(0.5, 0.955))
    fig.suptitle("Random Forest vs HistGradientBoosting – accuracy (top) and practical cost (bottom)", fontsize=17, color=INK, x=0.01, ha="left", y=0.995)
    fig.text(0.01, 0.005, test_desc, fontsize=10, color=MUTED)
    fig.tight_layout(rect=(0, 0.02, 1, 0.92), h_pad=3)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor="white")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare trained delay models and plot the results")
    parser.add_argument("--out", type=Path, default=Path("Assessment Reports/model_comparison.png"))
    parser.add_argument("--test-frac", type=float, default=0.2)
    args = parser.parse_args()

    engine = get_engine()
    df = read_table(engine, "model_dataset")
    engine.dispose()
    df["window_start"] = pd.to_datetime(df["window_start"], utc=True)

    accuracy, cost = evaluate(df, args.test_frac)
    for name, per_h in accuracy.items():
        row = "  ".join(f"{h}min MAE={m['mae']:.1f}s R2={m['r2']:.2f} off>1min={m['pct_off_1min']:.1f}%" for h, m in per_h.items())
        print(f"{LABELS[name]:32s} {row}")
    for name, c in cost.items():
        print(f"{LABELS[name]:32s} fit={c['fit_seconds']:.1f}s predict={c['predict_seconds']:.2f}s size={c['size_mb']:.1f}MB")

    test = chronological_split(df, args.test_frac)[1]["window_start"]
    desc = f"Test set: latest {args.test_frac:.0%} of {len(df):,} rows ({test.min():%d %b} – {test.max():%d %b %Y}). Timings measured on this machine."
    plot(accuracy, cost, args.out, desc)
    print(f"saved {args.out}")


if __name__ == "__main__":
    main()
