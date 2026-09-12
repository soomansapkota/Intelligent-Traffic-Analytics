import sqlite3

import pandas as pd

# vehicle_positions.speed is meters/second per the GTFS-Realtime spec, not
# km/h -- convert before comparing against a km/h threshold.
DEFAULT_CONGESTION_THRESHOLD_KMH = 10.0


def average_speed_by_route(conn: sqlite3.Connection, hours: int = 24) -> pd.DataFrame:
    """Summarize vehicle speed per route over the last N hours.

    vehicle_positions.speed is meters/second; convert to km/h (* 3.6) for
    a more readable metric.

    Args:
        conn: Open SQLite connection.
        hours: How far back to look, based on vehicle_positions.fetched_at.

    Returns:
        DataFrame with one row per route: route_id, route_short_name,
        mean_speed_kmh, n_observations.
    """
    raise NotImplementedError


def congestion_events(
    conn: sqlite3.Connection,
    speed_threshold_kmh: float = DEFAULT_CONGESTION_THRESHOLD_KMH,
    hours: int = 24,
) -> pd.DataFrame:
    """Flag vehicle position readings below a speed threshold as congested.

    A single slow reading isn't necessarily congestion (a vehicle stopped at
    a station reads near 0 speed) -- consider filtering out rows where
    current_status == "STOPPED_AT" before flagging, or requiring several
    consecutive slow readings for the same vehicle_id.

    Args:
        conn: Open SQLite connection.
        speed_threshold_kmh: Speed below which a reading counts as congested.
        hours: How far back to look, based on vehicle_positions.fetched_at.

    Returns:
        DataFrame with one row per flagged reading: vehicle_id, route_id,
        trip_id, speed_kmh, lat, lon, fetched_at.
    """
    raise NotImplementedError


def congestion_by_hour(conn: sqlite3.Connection, speed_threshold_kmh: float = DEFAULT_CONGESTION_THRESHOLD_KMH) -> pd.DataFrame:
    """Summarize the share of congested readings per hour of day (0-23).

    Convert vehicle_positions.timestamp (Unix seconds, UTC) to local time
    (Australia/Sydney) before extracting the hour.

    Args:
        conn: Open SQLite connection.
        speed_threshold_kmh: Speed below which a reading counts as congested.

    Returns:
        DataFrame with one row per hour (0-23): hour, pct_congested,
        n_observations.
    """
    raise NotImplementedError
