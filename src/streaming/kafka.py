import json
import logging
from typing import Any, Callable

import pandas as pd

from config.settings import KAFKA_BOOTSTRAP_SERVERS, KAFKA_GROUP_ID, KAFKA_TOPIC_PREFIX

logger = logging.getLogger(__name__)

FEEDS = ("trip_updates", "vehicle_positions", "alerts")

Handler = Callable[[str, dict[str, Any]], None]


def topic_for(feed: str) -> str:
    """Name the Kafka topic that carries one feed.

    Args:
        feed: Short feed name, e.g. "trip_updates".

    Returns:
        Topic string under the configured prefix. Kafka topic names cannot
        contain "/", so the prefix and feed are joined with "." instead.
    """
    return f"{KAFKA_TOPIC_PREFIX}.{feed}"


def connect_producer(bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS):
    """Create a Kafka producer.

    confluent_kafka is imported here rather than at module level so the
    rest of the pipeline runs without the broker dependency installed.

    Args:
        bootstrap_servers: Comma-separated host:port list of brokers.

    Returns:
        A confluent_kafka Producer.
    """
    from confluent_kafka import Producer

    return Producer({"bootstrap.servers": bootstrap_servers})


def connect_consumer(bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS, group_id: str = KAFKA_GROUP_ID):
    """Create a Kafka consumer.

    Args:
        bootstrap_servers: Comma-separated host:port list of brokers.
        group_id: Consumer group id, so restarts resume rather than replay
            from the beginning of the topic.

    Returns:
        A confluent_kafka Consumer. Not yet subscribed to any topic.
    """
    from confluent_kafka import Consumer

    return Consumer({
        "bootstrap.servers": bootstrap_servers,
        "group.id": group_id,
        "auto.offset.reset": "latest",
        "enable.auto.commit": True,
    })


def publish_feed(producer, feed: str, df: pd.DataFrame) -> int:
    """Publish every row of a decoded feed as its own JSON message.

    Blocks until every message is acknowledged by the broker (or the
    delivery is reported as failed), the same "do not drop records"
    guarantee the old MQTT qos=1 publishing gave.

    Args:
        producer: Connected Kafka producer, or anything with produce/flush/poll methods.
        feed: Short feed name, used to pick the topic.
        df: Decoded rows for that feed.

    Returns:
        Number of messages published.
    """
    topic = topic_for(feed)
    # Round-tripping through to_json turns NaN into null and timestamps into ISO strings.
    records = json.loads(df.to_json(orient="records", date_format="iso"))
    for record in records:
        producer.produce(topic, json.dumps(record).encode("utf-8"))
        producer.poll(0)  # serve delivery-report callbacks so the internal queue does not fill up
    producer.flush()
    return len(records)


def subscribe_feeds(consumer, feeds: tuple[str, ...] = FEEDS) -> None:
    """Subscribe a consumer to every given feed's topic.

    Args:
        consumer: Connected Kafka consumer, or anything with a subscribe method.
        feeds: Feed names to subscribe to.

    Returns:
        None.
    """
    consumer.subscribe([topic_for(feed) for feed in feeds])


def consume_forever(consumer, handler: Handler, poll_timeout: float = 1.0) -> None:
    """Poll the consumer forever, routing every message to a handler.

    Args:
        consumer: Subscribed Kafka consumer, or anything with poll/close methods.
        handler: Called as handler(feed, record) for each message.
        poll_timeout: Seconds to wait for a message before polling again.

    Returns:
        None.
    """
    try:
        while True:
            message = consumer.poll(poll_timeout)
            if message is None:
                continue
            if message.error():
                logger.warning(f"kafka consumer error: {message.error()}")
                continue
            feed = message.topic().rsplit(".", 1)[-1]
            handler(feed, json.loads(message.value()))
    except KeyboardInterrupt:
        logger.info("kafka consumer interrupted")
    finally:
        consumer.close()
