import pandas as pd

EPOCH = pd.Timestamp("1970-01-01", tz="UTC")

# GTFS convention: a service is "on time" within a minute either side.
ON_TIME_THRESHOLD_SECONDS = 60


def to_epoch_seconds(fetched_at: pd.Series) -> pd.Series:
    """Convert stored ISO timestamps to POSIX seconds.

    Args:
        fetched_at: Series of ISO 8601 strings as written by the storage layer.

    Returns:
        Series of POSIX seconds, aligned to the input index.
    """
    parsed = pd.to_datetime(fetched_at, utc=True, format="ISO8601")
    return (parsed - EPOCH).dt.total_seconds().astype("int64")


def to_window_start(fetched_at: pd.Series, freq: str = "1min") -> pd.Series:
    """Floor stored ISO timestamps onto the window grid.

    Args:
        fetched_at: Series of ISO 8601 strings as written by the storage layer.
        freq: Window size as a pandas offset alias.

    Returns:
        Series of UTC timestamps, one per row, floored to the window grid.
    """
    return pd.to_datetime(fetched_at, utc=True, format="ISO8601").dt.floor(freq)


def current_trip_delay(trip_updates_df: pd.DataFrame) -> pd.DataFrame:
    """Reduce each (poll, trip) pair to its freshest delay observation.

    A single poll carries every remaining stop of a trip, so arrival_delay
    mixes stops the train has already passed with predictions for stops up to
    two hours out. Only passed stops are measurements, and the far-future ones
    largely echo the schedule at zero delay, so averaging a whole poll pulls
    delay towards zero. The most recently passed stop is therefore the signal;
    trips yet to reach their first stop fall back to their next one and are
    flagged with is_passed=False so callers can exclude them.

    Args:
        trip_updates_df: Rows as stored in the trip_updates table.

    Returns:
        DataFrame with one row per (fetched_at, trip_id), carrying the chosen
        stop's arrival_delay alongside secs_to_arrival and is_passed.
    """
    df = trip_updates_df[trip_updates_df["arrival_time"] > 0].copy()
    if df.empty:
        return df

    df["fetched_ts"] = to_epoch_seconds(df["fetched_at"])
    df["secs_to_arrival"] = df["arrival_time"] - df["fetched_ts"]
    df["is_passed"] = df["secs_to_arrival"] <= 0
    df["secs_from_now"] = df["secs_to_arrival"].abs()

    ordered = df.sort_values(["is_passed", "secs_from_now"], ascending=[False, True])
    return ordered.groupby(["fetched_at", "trip_id"], as_index=False).first()


def build_windows(
    trip_delay_df: pd.DataFrame,
    vehicle_positions_df: pd.DataFrame,
    freq: str = "1min",
    on_time_threshold: int = ON_TIME_THRESHOLD_SECONDS,
    measured_only: bool = True,
) -> pd.DataFrame:
    """Aggregate per-trip delays and vehicle state into fixed time windows.

    Args:
        trip_delay_df: Output of current_trip_delay.
        vehicle_positions_df: Rows as stored in the vehicle_positions table.
        freq: Window size as a pandas offset alias.
        on_time_threshold: Delay in seconds above which a trip counts as late.
        measured_only: Drop trips that have not passed a stop yet. They report
            zero delay because nothing has been measured, and in the collected
            data they roughly halve the window mean.

    Returns:
        DataFrame with one row per (route_id, window_start) holding delay
        statistics across active trips and vehicle movement in that window.
    """
    delays = trip_delay_df[trip_delay_df["is_passed"]] if measured_only else trip_delay_df
    delays = delays.copy()
    delays["window_start"] = to_window_start(delays["fetched_at"], freq)
    delay_windows = delays.groupby(["route_id", "window_start"]).agg(
        mean_delay=("arrival_delay", "mean"),
        median_delay=("arrival_delay", "median"),
        max_delay=("arrival_delay", "max"),
        min_delay=("arrival_delay", "min"),
        p90_delay=("arrival_delay", lambda s: s.quantile(0.9)),
        frac_late=("arrival_delay", lambda s: (s > on_time_threshold).mean()),
        n_trips=("trip_id", "nunique"),
        n_polls=("fetched_at", "nunique"),
    )

    vehicles = vehicle_positions_df.copy()
    vehicles["window_start"] = to_window_start(vehicles["fetched_at"], freq)
    vehicle_windows = vehicles.groupby(["route_id", "window_start"]).agg(
        n_vehicles=("vehicle_id", "nunique"),
        mean_speed=("speed", "mean"),
        frac_stopped=("current_status", lambda s: (s == "STOPPED_AT").mean()),
    )

    windows = delay_windows.join(vehicle_windows, how="outer")
    return windows.reset_index().sort_values(["route_id", "window_start"], ignore_index=True)
