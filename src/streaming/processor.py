import argparse
import logging
from typing import Any

import pandas as pd
from sqlalchemy import Engine, text

from src.processing.windowing import build_windows, current_trip_delay
from src.storage.db import get_engine, init_db, write_alerts, write_trip_updates, write_vehicle_positions
from src.streaming.kafka import connect_consumer, consume_forever, subscribe_feeds

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {
    "trip_updates": (
        "entity_id", "trip_id", "route_id", "start_date", "stop_sequence", "stop_id",
        "arrival_time", "arrival_delay", "departure_time", "schedule_relationship",
    ),
    "vehicle_positions": (
        "entity_id", "trip_id", "route_id", "vehicle_id", "vehicle_label", "lat", "lon", "bearing",
        "speed", "current_stop_sequence", "current_status", "timestamp", "occupancy_status",
    ),
    "alerts": ("entity_id", "cause", "effect", "header_text", "description_text", "route_id"),
}

WRITERS = {
    "trip_updates": write_trip_updates,
    "vehicle_positions": write_vehicle_positions,
    "alerts": write_alerts,
}


class StreamProcessor:
    """Validate records arriving from the broker and store them in batches.

    Records that lack a required column are counted and dropped rather than
    written, so a malformed message cannot poison the tables downstream.
    """

    def __init__(self, engine: Engine, batch_size: int = 500) -> None:
        """Set up empty buffers for every known feed.

        Args:
            engine: SQLAlchemy engine for a database that already has the tables.
            batch_size: Rows to buffer per feed before writing.

        Returns:
            None.
        """
        self.engine = engine
        self.batch_size = batch_size
        self.buffers: dict[str, list[dict[str, Any]]] = {feed: [] for feed in REQUIRED_COLUMNS}
        self.rejected: dict[str, int] = {feed: 0 for feed in REQUIRED_COLUMNS}
        self.written: dict[str, int] = {feed: 0 for feed in REQUIRED_COLUMNS}

    def validate(self, feed: str, record: dict[str, Any]) -> bool:
        """Check that a record belongs to a known feed and has every required column.

        Args:
            feed: Feed name taken from the topic.
            record: Decoded JSON message.

        Returns:
            True if the record can be stored.
        """
        columns = REQUIRED_COLUMNS.get(feed)
        return columns is not None and all(column in record for column in columns)

    def handle(self, feed: str, record: dict[str, Any]) -> None:
        """Accept one record, buffering it or rejecting it.

        Args:
            feed: Feed name taken from the topic.
            record: Decoded JSON message.

        Returns:
            None.
        """
        if not self.validate(feed, record):
            self.rejected[feed] = self.rejected.get(feed, 0) + 1
            return
        self.buffers[feed].append(record)
        if len(self.buffers[feed]) >= self.batch_size:
            self.flush(feed)

    def flush(self, feed: str | None = None) -> None:
        """Write buffered records to the database.

        Args:
            feed: A single feed to flush, or None for all of them.

        Returns:
            None.
        """
        for name in [feed] if feed else list(self.buffers):
            rows = self.buffers[name]
            if not rows:
                continue
            WRITERS[name](self.engine, pd.DataFrame(rows))
            self.written[name] += len(rows)
            self.buffers[name] = []

    def current_windows(self, minutes: int = 15) -> pd.DataFrame:
        """Build one-minute windows over the most recently stored records.

        Args:
            minutes: How far back from now to include.

        Returns:
            Output of build_windows for that period, or an empty frame.
        """
        since = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=minutes)).isoformat()
        trip_updates = pd.read_sql(text("SELECT * FROM trip_updates WHERE fetched_at >= :since"), self.engine, params={"since": since})
        vehicles = pd.read_sql(text("SELECT * FROM vehicle_positions WHERE fetched_at >= :since"), self.engine, params={"since": since})
        delays = current_trip_delay(trip_updates)
        if delays.empty:
            return pd.DataFrame()
        return build_windows(delays, vehicles)


def run(batch_size: int = 500) -> None:
    """Subscribe to the broker and store records until interrupted.

    Args:
        batch_size: Rows to buffer per feed before writing.

    Returns:
        None.
    """
    engine = get_engine()
    init_db(engine)
    processor = StreamProcessor(engine, batch_size=batch_size)

    consumer = connect_consumer()
    subscribe_feeds(consumer)
    logger.info("stream processor listening")
    try:
        # Blocks polling until interrupted; consume_forever closes the consumer itself.
        consume_forever(consumer, processor.handle)
    finally:
        processor.flush()
        logger.info(f"written {processor.written} rejected {processor.rejected}")
        engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Consume feed records from the Kafka broker into the database")
    parser.add_argument("--batch-size", type=int, default=500, help="Rows to buffer per feed before writing")
    run(batch_size=parser.parse_args().batch_size)
