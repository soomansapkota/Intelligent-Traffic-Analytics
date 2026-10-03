import pandas as pd

from src.processing.windowing import to_window_start

DEFAULT_HORIZONS_MINUTES = (5, 10, 15)


def trip_delay_by_window(
    trip_delay_df: pd.DataFrame,
    freq: str = "1min",
    measured_only: bool = True,
) -> pd.DataFrame:
    """Reduce per-poll trip delays to one row per trip and window.

    The prediction unit is the individual trip, not the route. Averaging
    every trip on a route into one number per window cancelled the signal
    almost entirely in the collected data, keeping under 4% of its spread,
    whereas per-trip rows keep it and yield far more training examples.

    Args:
        trip_delay_df: Output of current_trip_delay.
        freq: Window size as a pandas offset alias.
        measured_only: Drop trips that have not passed a stop yet, since
            their zero delay is an absence of measurement rather than a value.

    Returns:
        DataFrame with one row per (route_id, trip_id, window_start) carrying
        the service day, the stop of the freshest observation, the mean
        arrival_delay, the furthest stop_sequence reached, and how stale the
        freshest observation was in seconds.
    """
    df = (
        trip_delay_df[trip_delay_df["is_passed"]]
        if measured_only
        else trip_delay_df
    )
    df = df.copy()
    df["window_start"] = to_window_start(df["fetched_at"], freq)
    # Sorted so that "last" picks the freshest observation, the one closest to its stop.
    df = df.sort_values(["route_id", "trip_id", "window_start", "secs_to_arrival"])
    return df.groupby(
        ["route_id", "trip_id", "window_start"], as_index=False
    ).agg(
        start_date=("start_date", "first"),
        stop_id=("stop_id", "last"),
        arrival_delay=("arrival_delay", "mean"),
        stop_sequence=("stop_sequence", "max"),
        secs_since_stop=("secs_to_arrival", lambda s: -s.max()),
    )


def add_trip_targets(
    trip_windows_df: pd.DataFrame,
    horizons_minutes: tuple[int, ...] = DEFAULT_HORIZONS_MINUTES,
) -> pd.DataFrame:
    """Attach each trip's own delay at every horizon as the prediction target.

    For each horizon a copy of the table is shifted back in time and left
    merged on (trip_id, window_start), so a row picks up the same trip's delay
    that many minutes later. Only forward lookups occur, so nothing leaks, and
    a trip that was not observed at the horizon keeps a null target rather
    than a filled one. Polling gaps therefore surface as missing labels.

    Args:
        trip_windows_df: Output of trip_delay_by_window.
        horizons_minutes: Prediction horizons in minutes.

    Returns:
        trip_windows_df with one target_delay_<h>min column per horizon.
    """
    lookup = trip_windows_df[["trip_id", "window_start", "arrival_delay"]]
    out = trip_windows_df.copy()
    for horizon in horizons_minutes:
        col = f"target_delay_{horizon}min"
        future = lookup.rename(columns={"arrival_delay": col})
        future = future.assign(
            window_start=future["window_start"] - pd.Timedelta(minutes=horizon)
        )
        out = out.merge(future, on=["trip_id", "window_start"], how="left")
    return out
