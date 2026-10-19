"""FastAPI server to expose real-time traffic data to mobile apps.

Endpoints:
- /api/alerts - Current service alerts
- /api/vehicles - Live vehicle positions (GPS + status)
- /api/delays - Latest predicted delays (5/10/15 min horizons)
- /api/routes - Sydney Metro route information
- /api/stations - Metro stations in line order
- /api/journey - Next trains between two stations, with live and predicted delay
"""

import math
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from src.api.journey import clock, delay_at_station, line_stations, live_only_departures, nearest_horizon, next_departures
from src.processing.features import SYDNEY_TZ
from src.processing.join_static import match_trips
from src.storage.db import get_engine, read_table

app = FastAPI(
    title="Traffic Analytics API",
    description="Real-time Sydney Metro delay predictions and vehicle tracking",
    version="1.0.0"
)

# Enable CORS for mobile app requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production: specify your app domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = get_engine()

_stations = None


def _get_stations() -> list[tuple[str, float, float]]:
    """Metro stations as (name, lat, lon), one per station rather than per platform.

    Loaded once from the static stops table: "Chatswood Station, Platform 2"
    and "..., Platform 3" collapse into "Chatswood Station" at their mean
    position. Empty until `--refresh-static` has been run.
    """
    global _stations
    if _stations is None:
        stops = pd.read_sql(text("SELECT stop_name, stop_lat, stop_lon FROM stops"), engine)
        stops["station"] = stops["stop_name"].str.split(",").str[0].str.strip()
        stops[["stop_lat", "stop_lon"]] = stops[["stop_lat", "stop_lon"]].astype(float)
        grouped = stops.groupby("station")[["stop_lat", "stop_lon"]].mean()
        _stations = [(name, row.stop_lat, row.stop_lon) for name, row in grouped.iterrows()]
    return _stations


def _nearest_station(lat: Optional[float], lon: Optional[float]) -> tuple[Optional[str], Optional[int]]:
    """Name of the closest station to a GPS point and its distance in metres."""
    stations = _get_stations()
    if lat is None or lon is None or not stations:
        return None, None

    def metres(s_lat, s_lon):
        # Haversine; plenty accurate over the few km between Metro stations.
        p1, p2 = math.radians(lat), math.radians(s_lat)
        a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(s_lon - lon) / 2) ** 2
        return 6_371_000 * 2 * math.asin(math.sqrt(a))

    name, distance = min(((n, metres(s_lat, s_lon)) for n, s_lat, s_lon in stations), key=lambda t: t[1])
    return name, round(distance)


STATIC_TABLES = ["stops", "trips", "stop_times", "calendar", "calendar_dates"]
_static = None


def _get_static() -> dict[str, pd.DataFrame]:
    """Static GTFS tables for the journey planner, loaded once.

    Like the station list, these only change on `--refresh-static`, after
    which the API needs a restart to pick them up.
    """
    global _static
    if _static is None:
        _static = {name: read_table(engine, name) for name in STATIC_TABLES}
        _static["line"] = line_stations(_static["stops"], _static["trips"], _static["stop_times"])
    return _static


def _live_trains(static: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """The latest predictions, keyed by the timetable trip each live train runs.

    Live trip ids differ from the timetable's between revisions, so they go
    through the same matching the dataset build uses.
    """
    live = pd.read_sql(text("SELECT * FROM predictions"), engine)
    if live.empty:
        return live.assign(static_trip_id=pd.Series(dtype=str))
    match = match_trips(live, static["trips"], static["calendar"], static["calendar_dates"], static["stop_times"])
    return live.merge(match[["trip_id", "start_date", "static_trip_id"]], on=["trip_id", "start_date"], how="left")


def _latest_feed(static: dict[str, pd.DataFrame], lookback_minutes: int = 3) -> pd.DataFrame:
    """Every train's most recent trip update, one row per listed stop.

    Includes trains that have not started their trip yet, which the
    predictions table leaves out. static_trip_id is attached the same way
    as for the predictions, and is missing for extra trains the published
    timetable does not have.
    """
    since = (datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)).isoformat()
    rows = pd.read_sql(text("""
        SELECT trip_id, start_date, stop_id, stop_sequence, arrival_time, arrival_delay, departure_time, fetched_at
        FROM trip_updates
        WHERE fetched_at > :since
    """), engine, params={"since": since})
    if rows.empty:
        return rows.assign(static_trip_id=pd.Series(dtype=str))
    rows = rows[rows["fetched_at"] == rows.groupby("trip_id")["fetched_at"].transform("max")]
    match = match_trips(rows, static["trips"], static["calendar"], static["calendar_dates"], static["stop_times"])
    return rows.merge(match[["trip_id", "start_date", "static_trip_id"]], on=["trip_id", "start_date"], how="left")


@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 503


@app.get("/api/alerts")
def get_alerts():
    """Get current service alerts.
    
    Returns:
        List of active alerts with cause, effect, and affected routes.
    """
    try:
        query = """
        SELECT DISTINCT
            entity_id,
            cause,
            effect,
            header_text,
            description_text,
            route_id,
            fetched_at
        FROM alerts
        WHERE fetched_at::timestamptz > now() - INTERVAL '1 hour'
        ORDER BY fetched_at DESC
        LIMIT 100
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(query))
            rows = result.fetchall()
            
        alerts = []
        for row in rows:
            alerts.append({
                "entity_id": row[0],
                "cause": row[1],
                "effect": row[2],
                "header": row[3],
                "description": row[4],
                "route_id": row[5],
                "fetched_at": row[6]
            })
        
        return {
            "alerts": alerts,
            "count": len(alerts),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/vehicles")
def get_vehicle_positions(route_id: Optional[str] = None):
    """Get current live vehicle positions.
    
    Args:
        route_id: Optional filter by route (e.g., "T1")
    
    Returns:
        List of vehicles with GPS coordinates, speed, status, trip info.
    """
    try:
        if route_id:
            query = f"""
            SELECT DISTINCT ON (vehicle_id)
                vehicle_id,
                vehicle_label,
                trip_id,
                route_id,
                lat,
                lon,
                bearing,
                speed,
                current_stop_sequence,
                current_status,
                occupancy_status,
                timestamp,
                fetched_at
            FROM vehicle_positions
            WHERE route_id = '{route_id}'
            ORDER BY vehicle_id, fetched_at DESC
            """
        else:
            query = """
            SELECT DISTINCT ON (vehicle_id)
                vehicle_id,
                vehicle_label,
                trip_id,
                route_id,
                lat,
                lon,
                bearing,
                speed,
                current_stop_sequence,
                current_status,
                occupancy_status,
                timestamp,
                fetched_at
            FROM vehicle_positions
            ORDER BY vehicle_id, fetched_at DESC
            LIMIT 200
            """
        
        with engine.connect() as conn:
            result = conn.execute(text(query))
            rows = result.fetchall()
        
        vehicles = []
        for row in rows:
            lat = float(row[4]) if row[4] is not None else None
            lon = float(row[5]) if row[5] is not None else None
            station, distance_m = _nearest_station(lat, lon)
            vehicles.append({
                "vehicle_id": row[0],
                "vehicle_label": row[1],
                "trip_id": row[2],
                "route_id": row[3],
                "latitude": lat,
                "longitude": lon,
                "nearest_station": station,
                "station_distance_m": distance_m,
                "bearing": float(row[6]) if row[6] is not None else None,
                "speed": float(row[7]) if row[7] is not None else None,
                "stop_sequence": row[8],
                "status": row[9],  # IN_TRANSIT, STOPPED_AT, INCOMING_AT
                "occupancy": row[10],
                "timestamp": row[11],
                "fetched_at": row[12]
            })
        
        return {
            "vehicles": vehicles,
            "count": len(vehicles),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/delays")
def get_predicted_delays(route_id: Optional[str] = None, horizon_minutes: int = 5):
    """Get latest delay predictions.
    
    Args:
        route_id: Optional filter by route
        horizon_minutes: Prediction horizon (5, 10, or 15)
    
    Returns:
        Latest predicted delays per trip with current status.
    """
    try:
        if horizon_minutes not in (5, 10, 15):
            horizon_minutes = 5

        prediction_col = f"predicted_delay_{horizon_minutes}min"
        query = f"""
        SELECT
            trip_id,
            route_id,
            window_start,
            arrival_delay as current_delay,
            {prediction_col} as predicted_delay,
            stop_id,
            stop_sequence,
            predicted_at,
            stop_name,
            trip_headsign
        FROM predictions
        WHERE (:route_id IS NULL OR route_id = :route_id)
        ORDER BY window_start DESC
        """

        with engine.connect() as conn:
            rows = conn.execute(text(query), {"route_id": route_id}).fetchall()

        to_minutes = lambda secs: round(float(secs) / 60, 2) if secs is not None else None
        delays = []
        for row in rows:
            delays.append({
                "trip_id": row[0],
                "route_id": row[1],
                "window_start": row[2].isoformat() if row[2] else None,
                "current_delay_minutes": to_minutes(row[3]),
                "predicted_delay_minutes": to_minutes(row[4]),
                "stop_id": row[5],
                "stop_sequence": row[6],
                # Station and destination come from the static timetable join, so
                # they are missing for the few trips that did not match it.
                "stop_name": row[8],
                "destination": row[9],
            })

        return {
            "horizon_minutes": horizon_minutes,
            "delays": delays,
            "count": len(delays),
            "predicted_at": rows[0][7].isoformat() if rows else None,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/routes")
def get_routes():
    """Get Sydney Metro routes.
    
    Returns:
        List of all routes with IDs and names.
    """
    try:
        query = """
        SELECT DISTINCT
            route_id,
            route_long_name
        FROM routes
        ORDER BY route_id
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(query))
            rows = result.fetchall()
        
        routes = []
        for row in rows:
            routes.append({
                "route_id": row[0],
                "route_name": row[1]
            })
        
        return {
            "routes": routes,
            "count": len(routes),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stations")
def get_stations():
    """Get the Metro stations in line order, for the journey planner's pickers."""
    try:
        stations = _get_static()["line"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"stations": stations, "count": len(stations), "timestamp": datetime.now().isoformat()}


@app.get("/api/journey")
def get_journey(
    from_station: str = Query(..., alias="from", description="Station to board at, as listed by /api/stations"),
    to_station: str = Query(..., alias="to", description="Station to get off at"),
    limit: int = Query(5, ge=1, le=20),
):
    """Get the next trains from one station to another.

    Times come from the timetable. When a train is already running, its
    current delay and the model's predicted delay are added: the horizon
    (5, 10 or 15 minutes) is whichever is closest to how far away the
    departure is, and the expected departure is the scheduled time plus
    that predicted delay. Trains not yet running show the timetable only.

    Extra trains TfNSW runs outside the published timetable are included
    too, timed from their own live trip update and marked in_timetable false.
    """
    try:
        static = _get_static()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    for station in (from_station, to_station):
        if station not in static["line"]:
            raise HTTPException(status_code=404, detail=f"Unknown station: {station}")
    if from_station == to_station:
        raise HTTPException(status_code=400, detail="From and to must be different stations")

    try:
        now = pd.Timestamp.now(tz=SYDNEY_TZ)
        now_seconds = (now - now.normalize()).total_seconds()
        # A few extra, since some turn out to have already left once live data is applied.
        scheduled = next_departures(
            from_station, to_station, now, static["stops"], static["trips"], static["stop_times"],
            static["calendar"], static["calendar_dates"], limit=limit + 5,
        )
        # Running trains, with the model's predictions.
        live = _live_trains(static)
        matched = live.dropna(subset=["static_trip_id"]).drop_duplicates(["static_trip_id", "start_date"])
        matched = matched.set_index(["static_trip_id", "start_date"])
        live_extra = live[live["static_trip_id"].isna()].drop_duplicates("trip_id").set_index("trip_id")

        # Every train in the feed, started or not, with TfNSW's forecast at the boarding station.
        feed = _latest_feed(static)
        forecast = delay_at_station(feed, static["stops"], from_station)
        feed_trips = feed.drop_duplicates("trip_id").set_index("trip_id")
        forecast_by_static = {
            (feed_trips.at[trip, "static_trip_id"], feed_trips.at[trip, "start_date"]): delay
            for trip, delay in forecast.items() if pd.notna(feed_trips.at[trip, "static_trip_id"])
        }
        extra_departures = live_only_departures(
            feed[feed["static_trip_id"].isna()], static["stops"], from_station, to_station, now.normalize(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # (departure, running train or None, TfNSW forecast or None, in the published timetable?), soonest first.
    candidates = [
        (dep,
         matched.loc[(dep.trip_id, dep.service_date)] if (dep.trip_id, dep.service_date) in matched.index else None,
         forecast_by_static.get((dep.trip_id, dep.service_date)),
         True)
        for dep in scheduled.itertuples()
    ] + [
        (dep, live_extra.loc[dep.trip_id] if dep.trip_id in live_extra.index else None, forecast.get(dep.trip_id), False)
        for dep in extra_departures.itertuples()
    ]
    candidates.sort(key=lambda c: c[0].departure_seconds)

    to_minutes = lambda secs: None if secs is None or pd.isna(secs) else round(float(secs) / 60, 2)
    departures = []
    for dep, train, tfnsw_forecast, in_timetable in candidates:
        minutes_ahead = (dep.departure_seconds - now_seconds) / 60
        horizon = current = predicted = None
        expected = dep.departure_seconds
        source = None

        if train is not None:
            if int(train["stop_sequence"]) > dep.origin_stop_sequence:
                continue  # already past the boarding station
            horizon = nearest_horizon(max(minutes_ahead, 0))
            current = train["arrival_delay"]
            predicted = train[f"predicted_delay_{horizon}min"]
            expected += predicted if pd.notna(predicted) else current
            source = "model"
        elif tfnsw_forecast is not None and pd.notna(tfnsw_forecast):
            # Not started yet, so nothing for the model to go on: fall back to TfNSW's own forecast.
            expected += tfnsw_forecast
            source = "tfnsw"
        if expected < now_seconds - 30:
            continue  # gone, or no live sign that it is still to come

        departures.append({
            "trip_id": dep.trip_id,
            "destination": dep.trip_headsign,
            "scheduled_departure": clock(dep.departure_seconds),
            "scheduled_arrival": clock(dep.arrival_seconds),
            "expected_departure": clock(expected),
            "duration_minutes": round((dep.arrival_seconds - dep.departure_seconds) / 60),
            "minutes_until_departure": round(max((expected - now_seconds) / 60, 0)),
            "live": train is not None,
            "in_timetable": in_timetable,
            "current_stop_name": None if train is None else train["stop_name"],
            "current_delay_minutes": to_minutes(current),
            "predicted_delay_minutes": to_minutes(predicted),
            "horizon_minutes": horizon,
            "forecast_delay_minutes": to_minutes(tfnsw_forecast),
            # What the expected time is based on: "model", "tfnsw", or None for the timetable alone.
            "delay_source": source,
        })
        if len(departures) == limit:
            break

    return {
        "from": from_station,
        "to": to_station,
        "departures": departures,
        "count": len(departures),
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/trip/{trip_id}")
def get_trip_details(trip_id: str):
    """Get detailed information for a specific trip.
    
    Args:
        trip_id: The trip ID to fetch
    
    Returns:
        Trip details including all stops, predicted delays at each horizon.
    """
    try:
        query = """
        SELECT
            trip_id,
            route_id,
            trip_headsign,
            start_date,
            window_start,
            arrival_delay,
            stop_id,
            stop_name,
            stop_sequence,
            predicted_delay_5min,
            predicted_delay_10min,
            predicted_delay_15min
        FROM predictions
        WHERE trip_id = :trip_id
        """

        with engine.connect() as conn:
            row = conn.execute(text(query), {"trip_id": trip_id}).fetchone()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not row:
        raise HTTPException(status_code=404, detail="Trip not found among the trains running now")

    to_minutes = lambda secs: round(float(secs) / 60, 2) if secs is not None else None
    return {
        "trip_id": row[0],
        "route_id": row[1],
        "destination": row[2],
        "service_date": row[3],
        "observed_time": row[4].isoformat() if row[4] else None,
        "current_delay_minutes": to_minutes(row[5]),
        "current_stop_id": row[6],
        "current_stop_name": row[7],
        "stop_sequence": row[8],
        "predicted_delays": {
            "5_minutes": to_minutes(row[9]),
            "10_minutes": to_minutes(row[10]),
            "15_minutes": to_minutes(row[11])
        },
        "timestamp": datetime.now().isoformat()
    }


@app.on_event("shutdown")
def shutdown():
    """Clean up database connection."""
    engine.dispose()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
