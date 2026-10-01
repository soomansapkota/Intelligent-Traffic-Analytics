import json
import sqlite3
import pandas as pd
import joblib

from src.storage.db import get_connection, read_table
from src.models.baseline import persistence_baseline
from src.models.train_ridge import build_ridge_pipeline
from src.models.validation import evaluate_rolling_origin

def run():
    conn = get_connection()
    try:
        df = read_table(conn, "trip_updates")
    except Exception:
        print("No trip_updates table found. Ensure ingestion has run.")
        return
    finally:
        conn.close()

    if df.empty or len(df) < 50:
        print("Not enough data to run validation yet.")
        return

    df = df.dropna(subset=["arrival_delay"])
    
    num_cols = ["stop_sequence", "arrival_delay"]
    cat_cols = ["route_id"] if "route_id" in df.columns else []
    
    X = df[num_cols + cat_cols]
    y = df["arrival_delay"]

    p_preds = persistence_baseline(df, "arrival_delay")
    baseline_mae = float((df["arrival_delay"] - p_preds).abs().mean())

    pipe = build_ridge_pipeline(num_cols, cat_cols, alpha=1.0)
    ridge_metrics = evaluate_rolling_origin(pipe, X, y, n_splits=5)

    results = {
        "baseline_mae": baseline_mae,
        "ridge_metrics": ridge_metrics
    }

    with open("experiments/results.json", "w") as f:
        json.dump(results, f, indent=4)

    pipe.fit(X, y)
    joblib.dump(pipe, "experiments/ridge_model_5m.joblib")
    
    print("Sulav's Modeling & Validation tasks completed successfully!")
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    run()

