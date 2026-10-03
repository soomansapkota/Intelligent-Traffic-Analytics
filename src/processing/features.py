import pandas as pd

SYDNEY_TZ = "Australia/Sydney"

DEFAULT_LAGS_MINUTES = (1, 2, 5)
DEFAULT_ROLLING_MINUTES = (5, 15)

# Weekday commuter peaks for Sydney Metro, in local hours.
AM_PEAK = (7, 9)
PM_PEAK = (16, 19)


def add_lag_features(
    trip_windows_df: pd.DataFrame,
    lags_minutes: tuple[int, ...] = DEFAULT_LAGS_MINUTES,
) -> pd.DataFrame:
    """Attach each trip's own delay from a fixed number of minutes earlier.

    Same shifted merge as the targets but pointing backwards, so a lag of
    five minutes is five minutes of wall clock rather than five rows, and a
    trip not observed at that moment keeps a null instead of a stale value.

    Args:
        trip_windows_df: Output of trip_delay_by_window.
        lags_minutes: How far back each lag looks, in minutes.

    Returns:
        trip_windows_df with one lag_delay_<k>min column per lag.
    """
    lookup = trip_windows_df[["trip_id", "window_start", "arrival_delay"]]
    out = trip_windows_df.copy()
    for lag in lags_minutes:
        col = f"lag_delay_{lag}min"
        past = lookup.rename(columns={"arrival_delay": col})
        past = past.assign(
            window_start=past["window_start"] + pd.Timedelta(minutes=lag)
        )
        out = out.merge(past, on=["trip_id", "window_start"], how="left")
    if 1 in lags_minutes:
        out["delay_change_1min"] = out["arrival_delay"] - out["lag_delay_1min"]
    return out


def add_rolling_features(
    trip_windows_df: pd.DataFrame,
    windows_minutes: tuple[int, ...] = DEFAULT_ROLLING_MINUTES,
) -> pd.DataFrame:
    """Attach per-trip rolling delay statistics over trailing time windows.

    Windows are time based and trail the current row, so they use only the
    present and past observations of the same trip.

    Args:
        trip_windows_df: Output of trip_delay_by_window.
        windows_minutes: Trailing window lengths in minutes.

    Returns:
        trip_windows_df with rolling_mean_<n>min and rolling_max_<n>min
        columns per window length, plus n_obs_<n>min giving how many
        observations fed each value.
    """
    keys = ["trip_id", "window_start"]
    ordered = trip_windows_df.sort_values(keys)
    # groupby.rolling with on= returns results keyed by (trip_id, window_start), so align on that key.
    keyed = ordered.set_index(keys)
    grouped = ordered.groupby("trip_id", group_keys=False)
    for minutes in windows_minutes:
        rolling = grouped.rolling(f"{minutes}min", on="window_start")["arrival_delay"]
        keyed[f"rolling_mean_{minutes}min"] = rolling.mean()
        keyed[f"rolling_max_{minutes}min"] = rolling.max()
        keyed[f"n_obs_{minutes}min"] = rolling.count().astype("int64")
    return keyed.reset_index().set_axis(ordered.index).sort_index()


def add_temporal_features(
    df: pd.DataFrame, time_col: str = "window_start"
) -> pd.DataFrame:
    """Attach time-of-day and calendar features in Sydney local time.

    Args:
        df: Any frame with a UTC timestamp column.
        time_col: Name of that column.

    Returns:
        df with hour, day_of_week, is_weekend and is_peak columns.
    """
    local = df[time_col].dt.tz_convert(SYDNEY_TZ)
    out = df.copy()
    out["hour"] = local.dt.hour
    out["day_of_week"] = local.dt.dayofweek
    out["is_weekend"] = out["day_of_week"] >= 5
    in_am = out["hour"].between(AM_PEAK[0], AM_PEAK[1] - 1)
    in_pm = out["hour"].between(PM_PEAK[0], PM_PEAK[1] - 1)
    out["is_peak"] = ~out["is_weekend"] & (in_am | in_pm)
    return out


def add_network_features(
    trip_windows_df: pd.DataFrame, windows_df: pd.DataFrame
) -> pd.DataFrame:
    """Attach route-wide window aggregates as context for each trip row.

    The route average is a poor target but a useful feature: it tells the
    model whether the whole line is running late around the trip in question.

    Args:
        trip_windows_df: Output of trip_delay_by_window.
        windows_df: Output of build_windows.

    Returns:
        trip_windows_df with the window aggregates joined on, prefixed net_.
    """
    keys = ["route_id", "window_start"]
    network = windows_df.set_index(keys).add_prefix("net_").reset_index()
    return trip_windows_df.merge(network, on=keys, how="left")
