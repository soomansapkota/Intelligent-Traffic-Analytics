import logging

from src.ingestion.fetch_feeds import fetch_alerts, fetch_trip_updates, fetch_vehicle_positions
from src.processing.decode_feeds import decode_alerts, decode_trip_updates, decode_vehicle_positions
from src.storage.db import get_connection, init_db, write_alerts, write_trip_updates, write_vehicle_positions

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run_once() -> None:
    """Fetch, decode, and store all three feeds once.

    Args:
        None.

    Returns:
        None.
    """
    conn = get_connection()
    init_db(conn)

    trip_updates_df = decode_trip_updates(fetch_trip_updates())
    write_trip_updates(conn, trip_updates_df)
    logger.info(f"trip_updates: wrote {len(trip_updates_df)} rows")

    vehicle_positions_df = decode_vehicle_positions(fetch_vehicle_positions())
    write_vehicle_positions(conn, vehicle_positions_df)
    logger.info(f"vehicle_positions: wrote {len(vehicle_positions_df)} rows")

    alerts_df = decode_alerts(fetch_alerts())
    write_alerts(conn, alerts_df)
    logger.info(f"alerts: wrote {len(alerts_df)} rows")

    conn.close()
    logger.info("pipeline cycle done")


if __name__ == "__main__":
    run_once()
