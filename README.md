# Intelligent Traffic Analytics

Real-time monitoring pipeline for Sydney Metro, built on TfNSW's GTFS-Realtime API.
Fetches trip updates, vehicle positions, and service alerts, then stores them in
PostgreSQL.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Start local Postgres and Kafka:

```bash
docker compose up -d
```

Create a `.env` file in the project root (see `.env.example`):

```
TFNSW_API_KEY=your_key_here

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=traffic
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_TOPIC_PREFIX=metro
KAFKA_GROUP_ID=traffic-analytics
```

Get a TfNSW key from https://opendata.transport.nsw.gov.au/. Point at a different
Postgres instance (a managed database, CI, etc.) by setting `DATABASE_URL` directly
instead of the individual `POSTGRES_*` variables -- it takes precedence when set.
Kafka is only needed for the streaming path below; the pipeline and dataset build
run fine without it.

## Run

Run one fetch cycle:

```bash
python -m src.orchestration.pipeline
```

Run continuously, fetching every 30 seconds:

```bash
python -m src.orchestration.scheduler
```

Download/refresh the static schedule (routes/trips/stops/stop_times, filtered to
Sydney Metro) -- run this once before your first realtime cycle, then occasionally
(e.g. daily) after that, since it changes far less often than the realtime feeds:

```bash
python -m src.orchestration.pipeline --refresh-static
```

Data is stored in the `traffic` Postgres database (see `docker-compose.yml`).

Build the `model_dataset` table (delay targets plus lag/rolling/temporal/network
features) from whatever has been collected so far -- run this after you have some
realtime cycles stored, and again whenever you want the dataset refreshed:

```bash
python -m src.orchestration.pipeline --build-dataset
```

## Delay prediction

Train one model per horizon (5/10/15 minutes) on `model_dataset`:

```bash
python -m src.modeling.train
```

This needs enough realtime history in `model_dataset` to have both training rows
and, later in time, test rows with a known target -- a handful of polling cycles
is not enough. Each model is a `HistGradientBoostingRegressor` (handles missing
lag/rolling features natively, no imputation needed), evaluated on a
chronological train/test split (never random -- these are time-ordered
observations) against a persistence baseline ("the delay stays the same"), so
the reported numbers show whether the model is actually worth having.

Output goes to `models/`: `delay_model_<horizon>min.joblib` per horizon,
`feature_columns.json` (the exact columns/order each model expects), and
`metrics.json` (MAE/RMSE/R2 for both the model and the baseline, per horizon).
Use `src/modeling/predict.py`'s `load_model`/`load_feature_columns`/`predict_delay`
to score new rows elsewhere (e.g. from a dashboard).

### Optional: Kafka streaming path

Publish each cycle's rows to Kafka in addition to writing them to Postgres:

```bash
python -m src.orchestration.pipeline --publish
```

Consume them elsewhere (a second process, machine, etc.) and store them as they arrive:

```bash
python -m src.streaming.processor
```

## Mobile App - Real-time Data Display

Display real-time traffic data on Android devices with **Java-based Android app** + **FastAPI backend**.

### Quick Start

**1. Start API Server:**

```bash
# Install FastAPI (already in requirements.txt)
pip install fastapi uvicorn

# Run the server
python -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000
```

Visit `http://localhost:8000/docs` for interactive API documentation.

**2. Open Android App in Android Studio:**

```bash
# Open the android folder in Android Studio
# Update server IP in: android/app/src/main/java/com/traffic/analytics/api/ApiClient.java
# Click Run to build and deploy
```

### Features

- **Service Alerts** - Real-time disruptions and maintenance notifications
- **Live Vehicle Tracking** - GPS locations, speed, status of all vehicles
- **Delay Predictions** - ML-powered delay forecasts (5/10/15 minute horizons)
- **Auto-refresh** - Updates every 20-30 seconds or on manual pull-to-refresh
- **Cross-platform** - Built with Retrofit (Java) for reliable networking

### Architecture

```
PostgreSQL Database
    ↓
FastAPI REST API (Python)
    ↓
Android App (Java)
```

### Setup Guides

- **[API Quick Start](API_QUICKSTART.md)** - Get the backend running in 2 minutes
- **[Mobile App Setup](MOBILE_APP_SETUP.md)** - Complete Android development guide
- **[Android Project Docs](android/README.md)** - Java source code and build instructions

### API Endpoints

| Endpoint | Response | Update Rate |
|----------|----------|------------|
| `/api/alerts` | Service disruptions | Every 30s |
| `/api/vehicles` | Live vehicle GPS/status | Every 20s |
| `/api/delays` | Predicted delays (5/10/15min) | Every 30s |
| `/api/routes` | Route info | Static |
| `/api/trip/{id}` | Trip details & predictions | On demand |

### Tech Stack

**Backend:**
- FastAPI 0.109.0
- Uvicorn (ASGI server)
- SQLAlchemy + PostgreSQL

**Android (Java):**
- Retrofit 2.10.0 (HTTP client)
- OkHttp 4.11.0 (Networking)
- RecyclerView (Data display)
- Android Lifecycle 2.7.0
- Material Design 3

### Screenshots (Planned Features)

1. **Alerts Screen** - Scrollable list of service disruptions
2. **Delays Screen** - Current + predicted delays by trip
3. **Vehicles Screen** - Live positions (GPS, speed, status)
