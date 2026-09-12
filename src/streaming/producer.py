import argparse
import logging
import time

from src.ingestion.fetch_feeds import fetch_alerts, fetch_trip_updates, fetch_vehicle_positions
from src.processing.decode_feeds import decode_alerts, decode_trip_updates, decode_vehicle_positions
from src.streaming.kafka_client import get_producer, publish_feed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Mirrors orchestration/pipeline.py's _FEEDS table, but publishes to Kafka
# instead of writing straight to SQLite -- src.streaming.processor is what
# consumes these topics and does the writing, on the other side of the broker.
_FEEDS = [
    ("trip_updates", fetch_trip_updates, decode_trip_updates),
    ("vehicle_positions", fetch_vehicle_positions, decode_vehicle_positions),
    ("alerts", fetch_alerts, decode_alerts),
]


def run_once(producer) -> None:
    """Fetch, decode, and publish all three feeds to Kafka once.

    Each feed is handled independently: if one fails, the others still run
    instead of the whole cycle aborting (same reasoning as pipeline.run_once).

    Args:
        producer: A connected KafkaProducer (see kafka_client.get_producer).

    Returns:
        None.
    """
    for name, fetch_fn, decode_fn in _FEEDS:
        try:
            df = decode_fn(fetch_fn())
            n = publish_feed(producer, name, df)
            logger.info(f"{name}: published {n} rows")
        except Exception:
            logger.exception(f"{name}: publish failed, skipping")


def run_forever(interval_seconds: int = 30) -> None:
    """Run the producer again and again, waiting between each run.

    Args:
        interval_seconds: Seconds to wait between runs. Minimum 15, so we
            do not poll the API faster than TfNSW updates its feeds.

    Returns:
        None.
    """
    interval_seconds = max(interval_seconds, 15)
    producer = get_producer()
    logger.info(f"starting kafka producer, interval={interval_seconds}s")
    try:
        while True:
            run_once(producer)
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        logger.info("producer stopped")
    finally:
        producer.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch feeds and publish them to Kafka")
    parser.add_argument("--interval", type=int, default=30, help="Seconds between fetch cycles")
    args = parser.parse_args()
    run_forever(interval_seconds=args.interval)
