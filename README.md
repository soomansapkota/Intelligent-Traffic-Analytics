# Intelligent Traffic Analytics

Real-time monitoring pipeline for Sydney Metro, built on TfNSW's GTFS-Realtime API.
Fetches trip updates, vehicle positions, and service alerts, then stores them in a
local SQLite database.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
TFNSW_API_KEY=your_key_here
```

Get a key from https://opendata.transport.nsw.gov.au/.

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

Data is stored in `data/traffic.db` (not committed to git).
