import pandas as pd

from src.processing.windowing import to_epoch_seconds


def poll_cadence(df: pd.DataFrame) -> pd.DataFrame:
    """Describe how regularly a feed was polled.

    Args:
        df: Rows from any realtime table, carrying a fetched_at column.

    Returns:
        Single-row DataFrame with the poll count, collection span, and the
        typical and worst gap between consecutive polls.
    """
    polls = pd.to_datetime(pd.Series(df["fetched_at"].unique()), utc=True, format="ISO8601").sort_values()
    gaps = polls.diff().dt.total_seconds().dropna()
    return pd.DataFrame([{
        "n_polls": len(polls),
        "first_poll": polls.min(),
        "last_poll": polls.max(),
        "span_minutes": (polls.max() - polls.min()).total_seconds() / 60,
        "median_gap_seconds": gaps.median(),
        "max_gap_seconds": gaps.max(),
    }])


def column_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Report null rate and cardinality for every column.

    Args:
        df: Any DataFrame.

    Returns:
        DataFrame indexed by column name with null_frac and n_unique.
    """
    return pd.DataFrame({
        "null_frac": df.isna().mean(),
        "n_unique": df.nunique(),
    })


def observation_share(trip_updates_df: pd.DataFrame) -> pd.DataFrame:
    """Split trip update rows into observed stops and forward predictions.

    Only stops the train has already passed carry a measured delay; the rest
    are the operator's own forecast, and the furthest ones mostly repeat the
    schedule at zero delay. The observed share is what limits how much real
    signal a collection run actually holds.

    Args:
        trip_updates_df: Rows as stored in the trip_updates table.

    Returns:
        DataFrame with one row per group (passed stops, upcoming stops) giving
        the row count, share of rows, and delay distribution within it.
    """
    df = trip_updates_df[trip_updates_df["arrival_time"] > 0].copy()
    df["secs_to_arrival"] = df["arrival_time"] - to_epoch_seconds(df["fetched_at"])
    df["stop_state"] = df["secs_to_arrival"].le(0).map({True: "passed", False: "upcoming"})

    summary = df.groupby("stop_state")["arrival_delay"].agg(
        n_rows="size", mean_delay="mean", min_delay="min", max_delay="max"
    )
    summary.insert(1, "row_share", summary["n_rows"] / len(df))
    return summary.reset_index()


def realtime_quality_report(
    trip_updates_df: pd.DataFrame,
    vehicle_positions_df: pd.DataFrame,
    alerts_df: pd.DataFrame,
) -> pd.DataFrame:
    """Summarise volume and cadence across the three realtime feeds.

    Args:
        trip_updates_df: Rows as stored in the trip_updates table.
        vehicle_positions_df: Rows as stored in the vehicle_positions table.
        alerts_df: Rows as stored in the alerts table.

    Returns:
        Tidy DataFrame of one row per (feed, metric).
    """
    feeds = {
        "trip_updates": trip_updates_df,
        "vehicle_positions": vehicle_positions_df,
        # Alerts are upserted rather than appended, so this feed reports the
        # current state of each alert, not a history of polls.
        "alerts": alerts_df,
    }

    rows = []
    for feed, df in feeds.items():
        cadence = poll_cadence(df).iloc[0]
        rows.append({
            "feed": feed,
            "n_rows": len(df),
            "n_polls": cadence["n_polls"],
            "span_minutes": round(cadence["span_minutes"], 1),
            "median_gap_seconds": cadence["median_gap_seconds"],
            "max_gap_seconds": cadence["max_gap_seconds"],
            "rows_per_poll": round(len(df) / cadence["n_polls"], 1),
        })

    return pd.DataFrame(rows)
