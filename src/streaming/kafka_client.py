import json
from typing import Any, Callable

import pandas as pd

from config.settings import KAFKA_BOOTSTRAP_SERVERS, KAFKA_CONSUMER_GROUP, KAFKA_TOPIC_PREFIX

FEEDS = ("trip_updates", "vehicle_positions", "alerts")

Handler = Callable[[str, dict[str, Any]], None]


def topic_for(feed: str) -> str:
    """Name the Kafka topic that carries one feed.

    Args:
        feed: Short feed name, e.g. "trip_updates".

    Returns:
        Topic string under the configured prefix.
    """
    return f"{KAFKA_TOPIC_PREFIX}.{feed}"


def get_producer(bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS):
    """Create a KafkaProducer that serializes values as JSON.

    kafka-python is imported here rather than at module level so the rest
    of the pipeline runs without the Kafka dependency installed.

    Args:
        bootstrap_servers: "host:port" (or comma-separated list) of the broker.

    Returns:
        A connected KafkaProducer.
    """
    from kafka import KafkaProducer

    return KafkaProducer(
        bootstrap_servers=bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        acks="all",
    )


def publish_feed(producer, feed: str, df: pd.DataFrame) -> int:
    """Publish every row of a decoded feed as its own JSON message.

    Args:
        producer: A KafkaProducer, or anything with a send(topic, value) method.
        feed: Short feed name, used to pick the topic.
        df: Decoded rows for that feed.

    Returns:
        Number of messages published.
    """
    topic = topic_for(feed)
    # Round-tripping through to_json turns NaN into null and timestamps into ISO strings.
    records = json.loads(df.to_json(orient="records", date_format="iso"))
    for record in records:
        producer.send(topic, value=record)
    producer.flush()
    return len(records)


def get_consumer(
    feeds: tuple[str, ...] = FEEDS,
    bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS,
    group_id: str = KAFKA_CONSUMER_GROUP,
):
    """Create a KafkaConsumer subscribed to the given feeds' topics.

    Args:
        feeds: Feed names to subscribe to.
        bootstrap_servers: "host:port" (or comma-separated list) of the broker.
        group_id: Consumer group id -- shared across processor instances so
            they split the partitions instead of each reading every message.

    Returns:
        A connected, subscribed KafkaConsumer that yields deserialized JSON values.
    """
    from kafka import KafkaConsumer

    topics = [topic_for(feed) for feed in feeds]
    return KafkaConsumer(
        *topics,
        bootstrap_servers=bootstrap_servers,
        group_id=group_id,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="latest",
        enable_auto_commit=True,
    )


def consume_feeds(consumer, handler: Handler) -> None:
    """Route every incoming message to a handler keyed by feed name.

    A Kafka consumer is a blocking iterator (pull model), unlike MQTT's
    callback-based push model, so this loops directly over it rather than
    registering an on_message callback. The loop runs until the consumer
    is closed or the caller interrupts it (e.g. KeyboardInterrupt).

    Args:
        consumer: A subscribed KafkaConsumer (see get_consumer).
        handler: Called as handler(feed, record) for each message.

    Returns:
        None.
    """
    for message in consumer:
        feed = message.topic.rsplit(".", 1)[-1]
        handler(feed, message.value)
