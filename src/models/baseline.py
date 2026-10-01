import pandas as pd
import numpy as np

def persistence_baseline(df: pd.DataFrame, target_col: str) -> np.ndarray:
    """Predicts future delay as equal to current delay."""
    return df["arrival_delay"].values

def route_average_baseline(df: pd.DataFrame, target_col: str) -> pd.Series:
    """Predicts future delay based on mean historical delay per route."""
    mean_delays = df.groupby("route_id")["arrival_delay"].transform("mean")
    return mean_delays