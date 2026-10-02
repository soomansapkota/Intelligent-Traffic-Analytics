"""Import a legacy SQLite traffic.db (trip_updates/vehicle_positions/alerts)
into the configured Postgres database, streaming in batches so a multi-GB
file doesn't need to fit in memory.

Usage:
    python -m scripts.import_sqlite_db <path-to-traffic.db> [--batch-size 50000]
"""

import argparse
import sqlite3
import sys
from pathlib import Path

from sqlalchemy import text

from src.storage.db import get_engine, init_db

TABLES = ["trip_updates", "vehicle_positions", "alerts"]

ALERTS_UPSERT = text("""
    INSERT INTO alerts (entity_id, cause, effect, header_text, description_text, route_id, fetched_at)
    VALUES (:entity_id, :cause, :effect, :header_text, :description_text, :route_id, :fetched_at)
    ON CONFLICT (entity_id, route_id) DO UPDATE SET
        cause=excluded.cause,
        effect=excluded.effect,
        header_text=excluded.header_text,
        description_text=excluded.description_text,
        fetched_at=excluded.fetched_at
""")


def import_table(sqlite_conn: sqlite3.Connection, engine, table: str, batch_size: int, skip_rows: int = 0) -> int:
    cursor = sqlite_conn.execute(f'SELECT * FROM "{table}" LIMIT -1 OFFSET {skip_rows}')
    columns = [d[0] for d in cursor.description]
    placeholders = ", ".join(f":{c}" for c in columns)
    col_list = ", ".join(columns)
    insert_stmt = text(f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders})')

    total = skip_rows
    if skip_rows:
        print(f"  {table}: resuming after {skip_rows:,} already-imported rows", flush=True)
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        batch = [dict(zip(columns, row)) for row in rows]
        with engine.begin() as conn:
            if table == "alerts":
                conn.execute(ALERTS_UPSERT, batch)
            else:
                conn.execute(insert_stmt, batch)
        total += len(batch)
        print(f"  {table}: {total:,} rows imported", flush=True)
    print(f"  {table}: {total:,} rows imported -> done", flush=True)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db_path", type=Path, help="Path to the SQLite traffic.db file")
    parser.add_argument("--batch-size", type=int, default=50_000, help="Rows per batch")
    parser.add_argument("--table", help="Import only this table (default: all)")
    parser.add_argument("--resume-table", help="Table to resume (skip already-imported rows in this table, then continue with the rest)")
    parser.add_argument("--skip-rows", type=int, default=0, help="Rows already imported into --resume-table")
    args = parser.parse_args()

    if not args.db_path.exists():
        sys.exit(f"No such file: {args.db_path}")

    engine = get_engine()
    init_db(engine)

    sqlite_conn = sqlite3.connect(args.db_path)
    try:
        tables = [args.table] if args.table else TABLES
        if args.resume_table and args.resume_table in tables:
            tables = tables[tables.index(args.resume_table):]
        for table in tables:
            print(f"Importing {table} from {args.db_path} ...")
            skip = args.skip_rows if table == args.resume_table else 0
            import_table(sqlite_conn, engine, table, args.batch_size, skip_rows=skip)
    finally:
        sqlite_conn.close()
        engine.dispose()


if __name__ == "__main__":
    main()
