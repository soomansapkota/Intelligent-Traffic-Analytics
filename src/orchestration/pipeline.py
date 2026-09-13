import argparse
import logging

from src.ingestion.fetch_feeds import (
    fetch_alerts,
    fetch_static_gtfs,
    fetch_trip_updates,
    fetch_vehicle_positions,
)
from src.processing.decode_feeds import (
    decode_alerts,
    decode_static_gtfs,
    decode_trip_updates,
    decode_vehicle_positions,
)
from src.processing.features import (
    add_lag_features,
    add_network_features,
    add_rolling_features,
    add_temporal_features,
)
from src.processing.join_static import attach_timetable, match_trips, stop_schedule
from src.processing.targets import add_trip_targets, trip_delay_by_window
from src.processing.windowing import build_windows, current_trip_delay
from src.storage.db import (
    get_engine,
    has_table,
    init_db,
    read_table,
    write_alerts,
    write_dataset,
    write_static_gtfs,
    write_trip_updates,
    write_vehicle_positions,
)
from src.streaming.kafka import connect_producer, publish_feed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

STATIC_TABLES = ("trips", "stops", "stop_times", "calendar", "calendar_dates")


def run_once(publish: bool = False) -> None:
    """Fetch, decode, and store all three feeds once.

    Args:
        publish: Also send every decoded row to the Kafka broker, so a
            stream processor elsewhere can consume the same records.

    Returns:
        None.
    """
    engine = get_engine()
    init_db(engine)
    producer = connect_producer() if publish else None

    trip_updates_df = decode_trip_updates(fetch_trip_updates())
    write_trip_updates(engine, trip_updates_df)
    logger.info(f"trip_updates: wrote {len(trip_updates_df)} rows")

    vehicle_positions_df = decode_vehicle_positions(fetch_vehicle_positions())
    write_vehicle_positions(engine, vehicle_positions_df)
    logger.info(f"vehicle_positions: wrote {len(vehicle_positions_df)} rows")

    alerts_df = decode_alerts(fetch_alerts())
    write_alerts(engine, alerts_df)
    logger.info(f"alerts: wrote {len(alerts_df)} rows")

    if producer is not None:
        for feed, df in [("trip_updates", trip_updates_df), ("vehicle_positions", vehicle_positions_df), ("alerts", alerts_df)]:
            logger.info(f"{feed}: published {publish_feed(producer, feed, df)} messages")

    engine.dispose()
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
    engine = get_engine()
    init_db(engine)

    tables = decode_static_gtfs(fetch_static_gtfs())
    write_static_gtfs(engine, tables)
    for name, df in tables.items():
        logger.info(f"static {name}: wrote {len(df)} rows")

    engine.dispose()


def build_dataset() -> None:
    """Turn the stored feeds into the model_dataset table.

    Realtime rows become one row per trip and minute carrying the delay
    targets plus lag, rolling, temporal and route-wide features. Timetable
    facts are joined on when the static schedule has been loaded, and
    skipped otherwise so the realtime part can still be built.

    Args:
        None.

    Returns:
        None.
    """
    engine = get_engine()
    init_db(engine)

    delays = current_trip_delay(read_table(engine, "trip_updates"))
    if delays.empty:
        logger.warning("no trip updates stored yet, nothing to build")
        engine.dispose()
        return

    windows = build_windows(delays, read_table(engine, "vehicle_positions"))
    dataset = trip_delay_by_window(delays)
    dataset = add_trip_targets(dataset)
    dataset = add_lag_features(dataset)
    dataset = add_rolling_features(dataset)
    dataset = add_temporal_features(dataset)
    dataset = add_network_features(dataset, windows)
    logger.info(f"realtime features: {len(dataset)} rows across {dataset['trip_id'].nunique()} trips")

    if all(has_table(engine, name) for name in STATIC_TABLES):
        static = {name: read_table(engine, name) for name in STATIC_TABLES}
        match = match_trips(dataset, static["trips"], static["calendar"], static["calendar_dates"], static["stop_times"])
        schedule = stop_schedule(static["stop_times"], static["trips"])
        dataset = attach_timetable(dataset, match, static["trips"], static["stops"], schedule)
        logger.info(f"timetable join: {match['match_method'].value_counts().to_dict()}")
    else:
        logger.warning("static schedule not loaded, run --refresh-static to add timetable features")

    write_dataset(engine, dataset)
    logger.info(f"model_dataset: wrote {len(dataset)} rows, {dataset.shape[1]} columns")
    engine.dispose()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Traffic analytics ingestion pipeline")
    parser.add_argument("--refresh-static", action="store_true", help="Download and store the static GTFS schedule instead of running a realtime cycle")
    parser.add_argument("--build-dataset", action="store_true", help="Build the model_dataset table from the stored feeds instead of running a realtime cycle")
    parser.add_argument("--publish", action="store_true", help="Also publish each decoded row to the Kafka broker during a realtime cycle")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.refresh_static:
        refresh_static_gtfs()
    elif args.build_dataset:
        build_dataset()
    else:
        run_once(publish=args.publish)
