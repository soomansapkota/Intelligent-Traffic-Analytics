"""FastAPI server to expose real-time traffic data to mobile apps.

Endpoints:
- /api/alerts - Current service alerts
- /api/vehicles - Live vehicle positions (GPS + status)
- /api/delays - Latest predicted delays (5/10/15 min horizons)
- /api/routes - Sydney Metro route information
"""

from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from config.settings import DELAY_MODEL_DIR
from src.modeling.predict import load_feature_columns, load_model, predict_delay
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

# Loaded on first use and kept, so each request does not re-read the
# (for random forests, ~80 MB) model files from disk.
_models = {}


def _get_model(horizon: int):
    if horizon not in _models:
        _models[horizon] = load_model(horizon, DELAY_MODEL_DIR)
    return _models[horizon]


def _model_name(model) -> str:
    return {"HistGradientBoostingRegressor": "hist_gradient_boosting", "RandomForestRegressor": "random_forest"}.get(
        type(model).__name__, type(model).__name__
    )


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
            WHERE route_id = :route_id
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
            result = conn.execute(text(query), {"route_id": route_id} if route_id else {})
            rows = result.fetchall()
        
        vehicles = []
        for row in rows:
            vehicles.append({
                "vehicle_id": row[0],
                "vehicle_label": row[1],
                "trip_id": row[2],
                "route_id": row[3],
                "latitude": float(row[4]) if row[4] is not None else None,
                "longitude": float(row[5]) if row[5] is not None else None,
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
    """Get the latest delay predictions from the trained model.

    Scores the newest model_dataset rows with the model in DELAY_MODEL_DIR
    (see config/settings.py). actual_delay_minutes is the delay that was
    later observed at that horizon, or null when it is still in the future,
    so predictions can be checked against it.

    Args:
        route_id: Optional filter by route
        horizon_minutes: Prediction horizon (5, 10, or 15)

    Returns:
        Latest predicted delays per trip with current status.
    """
    try:
        if horizon_minutes not in (5, 10, 15):
            horizon_minutes = 5

        try:
            model = _get_model(horizon_minutes)
            feature_columns = load_feature_columns(DELAY_MODEL_DIR)
        except FileNotFoundError as e:
            raise HTTPException(status_code=503, detail=str(e))

        where = "WHERE route_id = :route_id" if route_id else ""
        query = f"""
        SELECT *
        FROM model_dataset
        {where}
        ORDER BY window_start DESC
        LIMIT {50 if route_id else 100}
        """
        rows = pd.read_sql(text(query), engine, params={"route_id": route_id} if route_id else {})
        predicted = predict_delay(model, rows, feature_columns) if not rows.empty else pd.Series(dtype=float)

        # model_dataset stores delays in seconds; the API (and the Android
        # app) report minutes.
        def minutes(seconds):
            return None if pd.isna(seconds) else round(float(seconds) / 60, 2)

        delays = []
        for i, row in rows.iterrows():
            delays.append({
                "trip_id": row["trip_id"],
                "route_id": row["route_id"],
                "window_start": pd.Timestamp(row["window_start"]).isoformat() if pd.notna(row["window_start"]) else None,
                "current_delay_minutes": minutes(row["arrival_delay"]),
                "predicted_delay_minutes": minutes(predicted[i]),
                "actual_delay_minutes": minutes(row[f"target_delay_{horizon_minutes}min"]),
                "stop_id": row["stop_id"],
                "stop_sequence": None if pd.isna(row["stop_sequence"]) else int(row["stop_sequence"]),
            })

        return {
            "horizon_minutes": horizon_minutes,
            "model": _model_name(model),
            "delays": delays,
            "count": len(delays),
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
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
        query = f"""
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
            target_delay_5min,
            target_delay_10min,
            target_delay_15min
        FROM model_dataset
        WHERE trip_id = :trip_id
        ORDER BY window_start DESC
        LIMIT 1
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(query), {"trip_id": trip_id})
            row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Trip not found")
        
        return {
            "trip_id": row[0],
            "route_id": row[1],
            "destination": row[2],
            "service_date": row[3],
            "observed_time": row[4].isoformat() if row[4] else None,
            "current_delay_minutes": round(float(row[5]) / 60, 2) if row[5] is not None else None,
            "current_stop_id": row[6],
            "current_stop_name": row[7],
            "stop_sequence": row[8],
            "predicted_delays": {
                "5_minutes": round(float(row[9]) / 60, 2) if row[9] is not None else None,
                "10_minutes": round(float(row[10]) / 60, 2) if row[10] is not None else None,
                "15_minutes": round(float(row[11]) / 60, 2) if row[11] is not None else None
            },
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.on_event("shutdown")
def shutdown():
    """Clean up database connection."""
    engine.dispose()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
