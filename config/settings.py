import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")

# Absent rather than required, so the tests and the dataset build run without credentials. Fetching checks for it.
API_KEY = os.environ.get("TFNSW_API_KEY", "")
HEADERS = {"Authorization": f"apikey {API_KEY}"}

TRIP_UPDATES_URL = "https://api.transport.nsw.gov.au/v2/gtfs/realtime/metro"
VEHICLE_POS_URL = "https://api.transport.nsw.gov.au/v2/gtfs/vehiclepos/metro"
ALERTS_URL = "https://api.transport.nsw.gov.au/v2/gtfs/alerts/metro"

# Static schedule (routes/trips/stops/stop_times) covering all of NSW; we filter
# it down to Sydney Metro after download since there's no per-mode static feed.
STATIC_GTFS_URL = "https://api.transport.nsw.gov.au/v1/publictransport/timetables/complete/gtfs"
METRO_AGENCY_ID = "SMNW"

POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "traffic")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "postgres")

# Full connection string takes precedence when set, so a managed Postgres
# instance (Docker, RDS, Supabase, etc.) can be pointed at with one variable
# instead of five.
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}",
)

# Optional Kafka broker for the streaming layer. Nothing connects unless --publish is used or the stream processor is run.
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC_PREFIX = os.environ.get("KAFKA_TOPIC_PREFIX", "metro")
KAFKA_GROUP_ID = os.environ.get("KAFKA_GROUP_ID", "traffic-analytics")

# Retry behaviour for feed requests: up to MAX_RETRIES attempts, sleeping
# RETRY_BACKOFF_SECONDS * 2**attempt between them.
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", 3))
RETRY_BACKOFF_SECONDS = float(os.environ.get("RETRY_BACKOFF_SECONDS", 2))
