import json
import unittest

import pandas as pd
from sqlalchemy import create_engine, text

from src.storage.db import init_db
from src.streaming.kafka import consume_forever, publish_feed, subscribe_feeds, topic_for
from src.streaming.processor import StreamProcessor


class FakeProducer:
    def __init__(self):
        self.produced = []

    def produce(self, topic, value):
        self.produced.append((topic, value))

    def poll(self, timeout=0):
        pass  # would serve delivery-report callbacks for a real producer

    def flush(self):
        pass


class FakeMessage:
    def __init__(self, topic, value):
        self._topic = topic
        self._value = value

    def topic(self):
        return self._topic

    def value(self):
        return self._value

    def error(self):
        return None


class FakeConsumer:
    """Stands in for a confluent_kafka Consumer: queued messages, then done.

    Raising KeyboardInterrupt once the queue is empty mimics ending the
    poll loop the way an interrupt does for the real consumer, so
    consume_forever's normal shutdown path runs in tests too.
    """

    def __init__(self, messages=()):
        self.subscribed = []
        self._messages = list(messages)
        self.closed = False

    def subscribe(self, topics):
        self.subscribed = topics

    def poll(self, timeout=1.0):
        if not self._messages:
            raise KeyboardInterrupt
        return self._messages.pop(0)

    def close(self):
        self.closed = True


def _trip_update(trip_id="T", delay=10):
    return {
        "entity_id": trip_id, "trip_id": trip_id, "route_id": "SMNW_M1", "start_date": "20260815",
        "stop_sequence": 3, "stop_id": "S3", "arrival_time": 1786786200, "arrival_delay": delay,
        "departure_time": 0, "schedule_relationship": "SCHEDULED",
    }


class PublishTest(unittest.TestCase):
    def test_one_message_per_row_on_feed_topic(self):
        producer = FakeProducer()
        df = pd.DataFrame([_trip_update("A"), _trip_update("B")])
        count = publish_feed(producer, "trip_updates", df)
        self.assertEqual(count, 2)
        self.assertEqual(len(producer.produced), 2)
        self.assertTrue(all(topic == topic_for("trip_updates") for topic, _ in producer.produced))
        self.assertEqual(json.loads(producer.produced[0][1])["trip_id"], "A")

    def test_nan_becomes_null(self):
        producer = FakeProducer()
        df = pd.DataFrame([{"a": 1.0}, {"a": float("nan")}])
        publish_feed(producer, "vehicle_positions", df)
        self.assertIsNone(json.loads(producer.produced[1][1])["a"])


class SubscribeTest(unittest.TestCase):
    def test_subscribes_to_every_feed_topic(self):
        consumer = FakeConsumer()
        subscribe_feeds(consumer)
        self.assertEqual(consumer.subscribed, [topic_for(f) for f in ("trip_updates", "vehicle_positions", "alerts")])

    def test_routes_messages_to_handler_by_feed_and_closes_when_done(self):
        consumer = FakeConsumer([FakeMessage(topic_for("alerts"), json.dumps({"entity_id": "x"}).encode())])
        received = []
        consume_forever(consumer, lambda feed, record: received.append((feed, record)), poll_timeout=0)
        self.assertEqual(received, [("alerts", {"entity_id": "x"})])
        self.assertTrue(consumer.closed)


class StreamProcessorTest(unittest.TestCase):
    def setUp(self):
        # In-memory SQLite stands in for Postgres here: same SQLAlchemy code
        # path in db.py/processor.py, no server required for unit tests.
        self.engine = create_engine("sqlite://")
        init_db(self.engine)
        self.processor = StreamProcessor(self.engine, batch_size=2)

    def tearDown(self):
        self.engine.dispose()

    def _count(self, table):
        with self.engine.connect() as conn:
            return conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()

    def test_rejects_unknown_feed_and_missing_columns(self):
        self.processor.handle("nonsense", _trip_update())
        self.processor.handle("trip_updates", {"trip_id": "T"})
        self.assertEqual(self.processor.rejected["nonsense"], 1)
        self.assertEqual(self.processor.rejected["trip_updates"], 1)
        self.assertEqual(self._count("trip_updates"), 0)

    def test_writes_when_batch_fills(self):
        self.processor.handle("trip_updates", _trip_update("A"))
        self.assertEqual(self._count("trip_updates"), 0)
        self.processor.handle("trip_updates", _trip_update("B"))
        self.assertEqual(self._count("trip_updates"), 2)
        self.assertEqual(self.processor.written["trip_updates"], 2)

    def test_flush_writes_partial_batches_for_every_feed(self):
        self.processor.handle("trip_updates", _trip_update("A"))
        self.processor.handle("alerts", {
            "entity_id": "al1", "cause": "UNKNOWN_CAUSE", "effect": "UNKNOWN_EFFECT",
            "header_text": "h", "description_text": "d", "route_id": "SMNW_M1",
        })
        self.processor.flush()
        self.assertEqual(self._count("trip_updates"), 1)
        self.assertEqual(self._count("alerts"), 1)
        self.assertEqual(self.processor.buffers["trip_updates"], [])

    def test_current_windows_covers_recent_rows_only(self):
        now = int(pd.Timestamp.now(tz="UTC").timestamp())
        recent = _trip_update("A")
        recent["arrival_time"] = now - 60
        self.processor.handle("trip_updates", recent)
        self.processor.flush()
        windows = self.processor.current_windows(minutes=15)
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows.loc[0, "n_trips"], 1)
        self.assertEqual(windows.loc[0, "mean_delay"], 10)


if __name__ == "__main__":
    unittest.main()
