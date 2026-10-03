from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import Engine, create_engine, inspect, text

from config.settings import DATABASE_URL


def get_engine(database_url: str = DATABASE_URL) -> Engine:
    """Create a SQLAlchemy engine for the configured database.

    Points at Postgres by default (via DATABASE_URL / POSTGRES_* settings);
    tests pass an explicit sqlite:// URL instead so they run without a
    Postgres server.

    Args:
        database_url: SQLAlchemy connection URL.

    Returns:
        An Engine. Callers should dispose() it when done.
    """
    return create_engine(database_url)


def init_db(engine: Engine) -> None:
    """Create the tables if they do not already exist.

    Args:
        engine: SQLAlchemy engine.

    Returns:
        None.
    """
    with engine.begin() as conn:
        conn.execute(text("""
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
        """))
        conn.execute(text("""
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
        """))
        conn.execute(text("""
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
        """))

        # Indices for the queries analytics code will actually run: "give me
        # everything for this trip/route/vehicle" and "give me the latest cycle".
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_trip_updates_trip ON trip_updates (trip_id, fetched_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_trip_updates_route ON trip_updates (route_id, fetched_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_vehicle_positions_vehicle ON vehicle_positions (vehicle_id, fetched_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_vehicle_positions_route ON vehicle_positions (route_id, fetched_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_alerts_route ON alerts (route_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_trip_updates_fetched ON trip_updates (fetched_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_vehicle_positions_fetched ON vehicle_positions (fetched_at)"))


def write_static_gtfs(engine: Engine, tables: dict[str, pd.DataFrame]) -> None:
    """Replace the static schedule tables (routes/trips/stops/stop_times).

    Unlike the realtime writers, this replaces rather than appends: the
    static schedule is a full snapshot, not a stream of new events, and
    each refresh should fully supersede the previous one.

    Args:
        engine: SQLAlchemy engine.
        tables: Dict from decode_static_gtfs, keyed by table name.

    Returns:
        None.
    """
    for name, df in tables.items():
        df.to_sql(name, engine, if_exists="replace", index=False)

    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_trips_route ON trips (route_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_stop_times_trip ON stop_times (trip_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_stop_times_stop ON stop_times (stop_id)"))


def write_trip_updates(engine: Engine, df: pd.DataFrame) -> None:
    """Append trip update rows to the database.

    Args:
        engine: SQLAlchemy engine.
        df: DataFrame from decode_trip_updates.

    Returns:
        None.
    """
    df = df.copy()
    df["fetched_at"] = datetime.now(timezone.utc).isoformat()
    df.to_sql("trip_updates", engine, if_exists="append", index=False)


def write_vehicle_positions(engine: Engine, df: pd.DataFrame) -> None:
    """Append vehicle position rows to the database.

    Args:
        engine: SQLAlchemy engine.
        df: DataFrame from decode_vehicle_positions.

    Returns:
        None.
    """
    df = df.copy()
    df["fetched_at"] = datetime.now(timezone.utc).isoformat()
    df.to_sql("vehicle_positions", engine, if_exists="append", index=False)


def read_table(engine: Engine, table: str) -> pd.DataFrame:
    """Load a whole table into a DataFrame.

    Args:
        engine: SQLAlchemy engine.
        table: Table name to read.

    Returns:
        DataFrame holding every row of the table.

    Raises:
        ValueError: If the table name is not a plain identifier.
    """
    # A table name cannot be passed as a query parameter, so it is checked and quoted instead.
    if not table.isidentifier():
        raise ValueError(f"Invalid table name: {table!r}")
    return pd.read_sql(f'SELECT * FROM "{table}"', engine)


def read_recent(engine: Engine, table: str, since: datetime) -> pd.DataFrame:
    """Load only the rows fetched at or after a given time.

    fetched_at is stored as an ISO 8601 UTC string, so comparing it as text
    gives the same order as comparing the times themselves.

    Args:
        engine: SQLAlchemy engine.
        table: Table name to read, one with a fetched_at column.
        since: Earliest fetched_at to include, timezone-aware.

    Returns:
        DataFrame holding the matching rows.

    Raises:
        ValueError: If the table name is not a plain identifier.
    """
    if not table.isidentifier():
        raise ValueError(f"Invalid table name: {table!r}")
    cutoff = since.astimezone(timezone.utc).isoformat()
    return pd.read_sql(text(f'SELECT * FROM "{table}" WHERE fetched_at >= :cutoff'), engine, params={"cutoff": cutoff})


def write_predictions(engine: Engine, df: pd.DataFrame) -> None:
    """Replace the predictions table with the latest live predictions.

    Only the newest prediction per train is useful to the API, so each cycle
    overwrites the predictions table. The same rows are also appended to
    prediction_log, which keeps the history for checking accuracy later.

    Args:
        engine: SQLAlchemy engine.
        df: One row per train, from pipeline.predict_live.

    Returns:
        None.
    """
    df.to_sql("predictions", engine, if_exists="replace", index=False)
    df.to_sql("prediction_log", engine, if_exists="append", index=False)


def has_table(engine: Engine, table: str) -> bool:
    """Report whether a table exists in the database.

    Args:
        engine: SQLAlchemy engine.
        table: Table name to look for.

    Returns:
        True if the table exists.
    """
    return inspect(engine).has_table(table)


def write_dataset(engine: Engine, df: pd.DataFrame) -> None:
    """Replace the model_dataset table with a freshly built feature table.

    The dataset is derived entirely from the other tables, so it is rebuilt
    from scratch rather than appended to.

    Args:
        engine: SQLAlchemy engine.
        df: Feature table from the processing pipeline.

    Returns:
        None.
    """
    df.to_sql("model_dataset", engine, if_exists="replace", index=False)
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_model_dataset_trip ON model_dataset (trip_id, window_start)"))


def write_alerts(engine: Engine, df: pd.DataFrame) -> None:
    """Insert or update alert rows, keyed by entity_id and route_id.

    Args:
        engine: SQLAlchemy engine.
        df: DataFrame from decode_alerts.

    Returns:
        None.
    """
    fetched_at = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "entity_id": row.entity_id,
            "cause": row.cause,
            "effect": row.effect,
            "header_text": row.header_text,
            "description_text": row.description_text,
            "route_id": row.route_id,
            "fetched_at": fetched_at,
        }
        for row in df.itertuples()
    ]
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO alerts (entity_id, cause, effect, header_text, description_text, route_id, fetched_at)
            VALUES (:entity_id, :cause, :effect, :header_text, :description_text, :route_id, :fetched_at)
            ON CONFLICT(entity_id, route_id) DO UPDATE SET
                cause=excluded.cause,
                effect=excluded.effect,
                header_text=excluded.header_text,
                description_text=excluded.description_text,
                fetched_at=excluded.fetched_at
        """), rows)
