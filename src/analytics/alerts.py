import sqlite3

import pandas as pd


def active_alerts_by_route(conn: sqlite3.Connection) -> pd.DataFrame:
    """List the current alerts table joined against route names.

    The alerts table is already deduplicated by (entity_id, route_id) via
    upsert, so this is a straight join, not an aggregation.

    Args:
        conn: Open SQLite connection.

    Returns:
        DataFrame with one row per (alert, route): route_id,
        route_short_name, cause, effect, header_text, fetched_at.
    """
    raise NotImplementedError


def delay_during_active_alerts(conn: sqlite3.Connection, hours: int = 24) -> pd.DataFrame:
    """Compare average arrival delay for routes with vs without an active alert.

    This is the interesting correlation: does an open alert for a route
    actually coincide with worse delays on trip_updates for that route, or
    are alerts and delays independent in this data? Match on route_id and
    a fetched_at window (an alert and a trip_update don't need identical
    timestamps, just to be roughly concurrent).

    Args:
        conn: Open SQLite connection.
        hours: How far back to look.

    Returns:
        DataFrame with one row per route: route_id, route_short_name,
        has_active_alert, mean_delay_s, n_observations.
    """
    raise NotImplementedError
