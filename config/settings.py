import os

from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ["TFNSW_API_KEY"]
HEADERS = {"Authorization": f"apikey {API_KEY}"}

TRIP_UPDATES_URL = "https://api.transport.nsw.gov.au/v2/gtfs/realtime/metro"
VEHICLE_POS_URL = "https://api.transport.nsw.gov.au/v2/gtfs/vehiclepos/metro"
ALERTS_URL = "https://api.transport.nsw.gov.au/v2/gtfs/alerts/metro"

# Static schedule (routes/trips/stops/stop_times) covering all of NSW; we filter
# it down to Sydney Metro after download since there's no per-mode static feed.
STATIC_GTFS_URL = "https://api.transport.nsw.gov.au/v1/publictransport/timetables/complete/gtfs"
METRO_AGENCY_ID = "SMNW"

DB_PATH = "data/traffic.db"

# Retry behaviour for feed requests: up to MAX_RETRIES attempts, sleeping
# RETRY_BACKOFF_SECONDS * 2**attempt between them.
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", 3))
RETRY_BACKOFF_SECONDS = float(os.environ.get("RETRY_BACKOFF_SECONDS", 2))

# Kafka broker used by src/streaming: the producer publishes decoded feed rows
# to topics under KAFKA_TOPIC_PREFIX, and the stream processor consumes them.
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC_PREFIX = os.environ.get("KAFKA_TOPIC_PREFIX", "traffic")
KAFKA_CONSUMER_GROUP = os.environ.get("KAFKA_CONSUMER_GROUP", "traffic-stream-processor")
