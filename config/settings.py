import os

from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ["TFNSW_API_KEY"]
HEADERS = {"Authorization": f"apikey {API_KEY}"}

TRIP_UPDATES_URL = "https://api.transport.nsw.gov.au/v2/gtfs/realtime/metro"
VEHICLE_POS_URL = "https://api.transport.nsw.gov.au/v2/gtfs/vehiclepos/metro"
ALERTS_URL = "https://api.transport.nsw.gov.au/v2/gtfs/alerts/metro"

DB_PATH = "data/traffic.db"
