import sqlite3
from datetime import datetime, timezone

import pandas as pd

from config.settings import DB_PATH


def get_connection() -> sqlite3.Connection:
    """Open a connection to the local SQLite database.

    Args:
        None.

    Returns:
        An open SQLite connection.
    """
    return sqlite3.connect(DB_PATH)


def init_db(conn: sqlite3.Connection) -> None:
    """Create the tables if they do not already exist.

    Args:
        conn: Open SQLite connection.

    Returns:
        None.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trip_updates (
            entity_id TEXT,
            trip_id TEXT,
            route_id TEXT,
            start_date TEXT,
            stop_sequence INTEGER,
            stop_id TEXT,
            arrival_time INTEGER,
            arrival_delay INTEGER,
            departure_time INTEGER,
            schedule_relationship TEXT,
            fetched_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vehicle_positions (
            entity_id TEXT,
            trip_id TEXT,
            route_id TEXT,
            vehicle_id TEXT,
            vehicle_label TEXT,
            lat REAL,
            lon REAL,
            bearing REAL,
            speed REAL,
            current_stop_sequence INTEGER,
            current_status TEXT,
            timestamp INTEGER,
            occupancy_status TEXT,
            fetched_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            entity_id TEXT,
            cause TEXT,
            effect TEXT,
            header_text TEXT,
            description_text TEXT,
            route_id TEXT,
            fetched_at TEXT,
            PRIMARY KEY (entity_id, route_id)
        )
    """)
    conn.commit()


def write_trip_updates(conn: sqlite3.Connection, df: pd.DataFrame) -> None:
    """Append trip update rows to the database.

    Args:
        conn: Open SQLite connection.
        df: DataFrame from decode_trip_updates.

    Returns:
        None.
    """
    df = df.copy()
    df["fetched_at"] = datetime.now(timezone.utc).isoformat()
    df.to_sql("trip_updates", conn, if_exists="append", index=False)


def write_vehicle_positions(conn: sqlite3.Connection, df: pd.DataFrame) -> None:
    """Append vehicle position rows to the database.

    Args:
        conn: Open SQLite connection.
        df: DataFrame from decode_vehicle_positions.

    Returns:
        None.
    """
    df = df.copy()
    df["fetched_at"] = datetime.now(timezone.utc).isoformat()
    df.to_sql("vehicle_positions", conn, if_exists="append", index=False)


def write_alerts(conn: sqlite3.Connection, df: pd.DataFrame) -> None:
    """Insert or update alert rows, keyed by entity_id and route_id.

    Args:
        conn: Open SQLite connection.
        df: DataFrame from decode_alerts.

    Returns:
        None.
    """
    fetched_at = datetime.now(timezone.utc).isoformat()
    rows = [
        (row.entity_id, row.cause, row.effect, row.header_text, row.description_text, row.route_id, fetched_at)
        for row in df.itertuples()
    ]
    conn.executemany("""
        INSERT INTO alerts (entity_id, cause, effect, header_text, description_text, route_id, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(entity_id, route_id) DO UPDATE SET
            cause=excluded.cause,
            effect=excluded.effect,
            header_text=excluded.header_text,
            description_text=excluded.description_text,
            fetched_at=excluded.fetched_at
    """, rows)
    conn.commit()
