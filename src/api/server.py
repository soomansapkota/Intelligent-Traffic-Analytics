"""FastAPI server to expose real-time traffic data to mobile apps.

Endpoints:
- /api/alerts - Current service alerts
- /api/vehicles - Live vehicle positions (GPS + status)
- /api/delays - Latest predicted delays (5/10/15 min horizons)
- /api/routes - Sydney Metro route information
"""

import math
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from src.storage.db import get_engine

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
