import sqlite3

import pandas as pd


def delay_by_route(conn: sqlite3.Connection, hours: int = 24) -> pd.DataFrame:
    """Summarize arrival delay per route over the last N hours.

    trip_updates.arrival_delay is in seconds, positive = late, negative =
    early (per the GTFS-Realtime spec). Join against routes.route_short_name
    for a human-readable label instead of raw route_id.

    Args:
        conn: Open SQLite connection.
        hours: How far back to look, based on trip_updates.fetched_at.

    Returns:
        DataFrame with one row per route: route_id, route_short_name,
        mean_delay_s, p90_delay_s, n_observations (suggested columns --
        adjust as your analysis needs).
    """
    raise NotImplementedError


def delay_by_hour_of_day(conn: sqlite3.Connection, route_id: str | None = None) -> pd.DataFrame:
    """Summarize arrival delay bucketed by hour of day (0-23).

    Useful for spotting peak-hour vs off-peak patterns. arrival_time is a
    Unix timestamp (seconds) -- convert to local time (Australia/Sydney)
    before extracting the hour, not UTC, or peak-hour buckets will be off.

    Args:
        conn: Open SQLite connection.
        route_id: If given, restrict to this route; otherwise all routes.

    Returns:
        DataFrame with one row per hour (0-23): hour, mean_delay_s,
        n_observations.
    """
    raise NotImplementedError


def worst_delayed_stops(conn: sqlite3.Connection, hours: int = 24, top_n: int = 10) -> pd.DataFrame:
    """Find the stops with the highest average arrival delay.

    Join trip_updates.stop_id against stops.stop_name for readability.

    Args:
        conn: Open SQLite connection.
        hours: How far back to look, based on trip_updates.fetched_at.
        top_n: Number of stops to return, sorted worst-first.

    Returns:
        DataFrame with one row per stop: stop_id, stop_name, mean_delay_s,
        n_observations.
    """
    raise NotImplementedError
