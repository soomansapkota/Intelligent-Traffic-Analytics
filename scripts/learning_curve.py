"""Learning curve: does more training data lower the error?

Trains a model on growing slices of the training data (the most recent
25%, 50% and 100% by default) and scores every slice on the same test set,
so the only thing that changes is how much history the model saw. A curve
still falling at 100% means collecting more data should keep helping.

    python -m scripts.learning_curve
    python -m scripts.learning_curve --model hist_gradient_boosting --fractions 0.1 0.25 0.5 1.0

Fits one model per fraction per horizon (about 4 minutes for the default
random forest); the saved models in models/ are not touched.
"""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.modeling.train import MODELS, build_xy, chronological_split, regression_metrics, select_feature_columns
from src.processing.targets import DEFAULT_HORIZONS_MINUTES
from src.storage.db import get_engine, read_table

# One fixed colour per horizon, from the same validated palette as compare_models.
HORIZON_COLORS = {5: "#00897B", 10: "#C96A0A", 15: "#5C6BC0"}
INK, MUTED, GRID = "#1B2B34", "#6B7C86", "#E3E8EA"


def learning_curve(df: pd.DataFrame, model_name: str, fractions: list[float], test_frac: float) -> pd.DataFrame:
    """Score a model trained on each fraction of the training data.

    Each fraction keeps the most recent slice of the training period, so
    every model is tested on the period straight after what it learned from.

    Returns:
        One row per (fraction, horizon) with n_train, days, mae, r2 and
        pct_off_1min.
    """
    columns = select_feature_columns(df)
    train_df, test_df = chronological_split(df, test_frac)
    rows = []
    for frac in fractions:
        subset = train_df.iloc[int(len(train_df) * (1 - frac)):]
        days = (subset["window_start"].max() - subset["window_start"].min()).total_seconds() / 86400
        for h in DEFAULT_HORIZONS_MINUTES:
            x, y = build_xy(subset, h, columns)
            x_test, y_test = build_xy(test_df, h, columns)
            pred = MODELS[model_name]().fit(x, y).predict(x_test)
            m = regression_metrics(y_test, pred)
            rows.append({
                "fraction": frac, "horizon": h, "n_train": len(x), "days": days,
                "mae": m["mae"], "r2": m["r2"], "pct_off_1min": float((np.abs(pred - y_test) > 60).mean() * 100),
            })
            print(f"{frac:>5.0%} ({len(x):>7,} rows, ~{days:.1f} days)  {h:>2}min  MAE={m['mae']:.1f}s  R2={m['r2']:.2f}")
    return pd.DataFrame(rows)


def plot(results: pd.DataFrame, model_name: str, out: Path) -> None:
    plt.rcParams.update({"font.family": ["Calibri", "DejaVu Sans"], "font.size": 11, "axes.edgecolor": GRID, "xtick.color": MUTED, "ytick.color": MUTED})
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), dpi=200)
    label = model_name.replace("_", " ").title()

    for ax, key, title in ((axes[0], "mae", "MAE (seconds) – lower is better"), (axes[1], "r2", "R² – higher is better")):
        for h, color in HORIZON_COLORS.items():
            sub = results[results["horizon"] == h]
            xs = sub["fraction"] * 100
            ax.plot(xs, sub[key], color=color, linewidth=2, marker="o", markersize=8, markeredgecolor="white", markeredgewidth=2, label=f"{h}-min horizon")
            last = sub.iloc[-1]
            ax.annotate(f"{last[key]:.1f}s" if key == "mae" else f"{last[key]:.2f}", (last["fraction"] * 100, last[key]),
                        xytext=(8, 0), textcoords="offset points", va="center", fontsize=10, color=INK)
        ax.set_title(title, color=INK, fontsize=13, loc="left", pad=10)
        ax.set_xlabel("Share of training data used (%)", color=MUTED)
        ax.set_xticks(sorted(results["fraction"].unique() * 100))
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.yaxis.grid(True, color=GRID, linewidth=0.6)
        ax.tick_params(length=0)
        ax.set_xlim(right=results["fraction"].max() * 100 * 1.1)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, frameon=False, fontsize=12, bbox_to_anchor=(0.5, 0.93))
    fig.suptitle(f"Learning curve – {label}: more data, lower error", fontsize=16, color=INK, x=0.01, ha="left", y=0.99)
    full = results[results["fraction"] == results["fraction"].max()].iloc[0]
    fig.text(0.01, 0.01, f"Each point: model trained on the most recent share of the training data, tested on the same held-out period. "
             f"100% = {int(full['n_train']):,} rows (~{full['days']:.0f} days).", fontsize=10, color=MUTED)
    fig.tight_layout(rect=(0, 0.04, 1, 0.86))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor="white")


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot how model error changes with the amount of training data")
    parser.add_argument("--model", choices=sorted(MODELS), default="random_forest")
    parser.add_argument("--fractions", type=float, nargs="+", default=[0.25, 0.5, 1.0])
    parser.add_argument("--test-frac", type=float, default=0.2)
    parser.add_argument("--out", type=Path, default=Path("Assessment Reports/learning_curve.png"))
    args = parser.parse_args()

    engine = get_engine()
    df = read_table(engine, "model_dataset")
    engine.dispose()
    df["window_start"] = pd.to_datetime(df["window_start"], utc=True)

    results = learning_curve(df, args.model, sorted(args.fractions), args.test_frac)
    plot(results, args.model, args.out)
    print(f"saved {args.out}")


if __name__ == "__main__":
    main()
