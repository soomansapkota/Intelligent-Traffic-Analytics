import argparse
import logging

from src.ingestion.fetch_feeds import fetch_alerts, fetch_static_gtfs, fetch_trip_updates, fetch_vehicle_positions
from src.processing.decode_feeds import decode_alerts, decode_static_gtfs, decode_trip_updates, decode_vehicle_positions
from src.storage.db import get_connection, init_db, write_alerts, write_static_gtfs, write_trip_updates, write_vehicle_positions

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Each feed is (name, fetch_fn, decode_fn, write_fn). Kept as a table so
# run_once can loop over it and one feed's failure doesn't block the others.
_FEEDS = [
    ("trip_updates", fetch_trip_updates, decode_trip_updates, write_trip_updates),
    ("vehicle_positions", fetch_vehicle_positions, decode_vehicle_positions, write_vehicle_positions),
    ("alerts", fetch_alerts, decode_alerts, write_alerts),
]


def run_once() -> None:
    """Fetch, decode, and store all three feeds once.

    Each feed is handled independently: if one fails (e.g. the API returns
    a transient error), the others still run instead of the whole cycle
    aborting.

    Args:
        None.

    Returns:
        None.
    """
    conn = get_connection()
    init_db(conn)

    for name, fetch_fn, decode_fn, write_fn in _FEEDS:
        try:
            df = decode_fn(fetch_fn())
            write_fn(conn, df)
            logger.info(f"{name}: wrote {len(df)} rows")
        except Exception:
            logger.exception(f"{name}: cycle failed, skipping")

    conn.close()
    logger.info("pipeline cycle done")


def refresh_static_gtfs() -> None:
    """Download the static schedule and replace the routes/trips/stops/stop_times tables.

    The static schedule changes rarely (timetable updates), so this is meant
    to be run on its own -- daily, or by hand -- not every realtime cycle.

    Args:
        None.

    Returns:
        None.
    """
    conn = get_connection()
    init_db(conn)

    tables = decode_static_gtfs(fetch_static_gtfs())
    write_static_gtfs(conn, tables)
    for name, df in tables.items():
        logger.info(f"static {name}: wrote {len(df)} rows")

    conn.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Traffic analytics ingestion pipeline")
    parser.add_argument("--refresh-static", action="store_true", help="Download and store the static GTFS schedule instead of running a realtime cycle")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.refresh_static:
        refresh_static_gtfs()
    else:
        run_once()
