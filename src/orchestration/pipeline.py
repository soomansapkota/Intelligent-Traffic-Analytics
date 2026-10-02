import argparse
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from src.ingestion.fetch_feeds import (
    fetch_alerts,
    fetch_static_gtfs,
    fetch_trip_updates,
    fetch_vehicle_positions,
)
from src.processing.decode_feeds import (
    decode_alerts,
    decode_static_gtfs,
    decode_trip_updates,
    decode_vehicle_positions,
)
from src.processing.features import (
    add_lag_features,
    add_network_features,
    add_rolling_features,
    add_temporal_features,
)
from src.modeling.predict import DEFAULT_MODEL_DIR, load_feature_columns, load_model, predict_delay
from src.processing.join_static import attach_timetable, match_trips, stop_schedule
from src.processing.targets import DEFAULT_HORIZONS_MINUTES, add_trip_targets, trip_delay_by_window
from src.processing.windowing import build_windows, current_trip_delay
from src.storage.db import (
    get_engine,
    has_table,
    init_db,
    read_recent,
    read_table,
    write_alerts,
    write_dataset,
    write_predictions,
    write_static_gtfs,
    write_trip_updates,
    write_vehicle_positions,
)
from src.streaming.kafka import connect_producer, publish_feed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

STATIC_TABLES = ("trips", "stops", "stop_times", "calendar", "calendar_dates")

LIVE_LOOKBACK_MINUTES = 20
LIVE_MAX_AGE_MINUTES = 2


def run_once(publish: bool = False, predict: bool = False) -> None:
    """Fetch, decode, and store all three feeds once.

    Args:
        publish: Also send every decoded row to the Kafka broker, so a
            stream processor elsewhere can consume the same records.
        predict: Also predict the delay of every live train from the
            saved models and store it in the predictions table.

    Returns:
        None.
    """
    engine = get_engine()
    init_db(engine)
    producer = connect_producer() if publish else None

    trip_updates_df = decode_trip_updates(fetch_trip_updates())
    write_trip_updates(engine, trip_updates_df)
    logger.info(f"trip_updates: wrote {len(trip_updates_df)} rows")

    vehicle_positions_df = decode_vehicle_positions(fetch_vehicle_positions())
    write_vehicle_positions(engine, vehicle_positions_df)
    logger.info(f"vehicle_positions: wrote {len(vehicle_positions_df)} rows")

    alerts_df = decode_alerts(fetch_alerts())
    write_alerts(engine, alerts_df)
    logger.info(f"alerts: wrote {len(alerts_df)} rows")

    if producer is not None:
        for feed, df in [("trip_updates", trip_updates_df), ("vehicle_positions", vehicle_positions_df), ("alerts", alerts_df)]:
            logger.info(f"{feed}: published {publish_feed(producer, feed, df)} messages")

    if predict:
        try:
            predictions = predict_live(engine)
            if predictions.empty:
                logger.info("predictions: no live trains this cycle")
            else:
                write_predictions(engine, predictions)
                logger.info(f"predictions: wrote {len(predictions)} live trains")
        except FileNotFoundError as e:
            logger.warning(f"skipping predictions: {e}")
        except Exception:
            logger.exception("prediction failed, collection carries on")

    engine.dispose()
    logger.info("pipeline cycle done")


def refresh_static_gtfs() -> None:
    """Download the static schedule and replace the routes/trips/stops/stop_times tables.

    The static schedule changes rarely (timetable updates), so this is meant
    to be run on its own -- daily, or by hand -- not every realtime cycle.

    Args:
        None.

    Returns:
        None.
    """
    engine = get_engine()
    init_db(engine)

    tables = decode_static_gtfs(fetch_static_gtfs())
    write_static_gtfs(engine, tables)
    for name, df in tables.items():
        logger.info(f"static {name}: wrote {len(df)} rows")

    engine.dispose()


def build_dataset() -> None:
    """Turn the stored feeds into the model_dataset table.

    Realtime rows become one row per trip and minute carrying the delay
    targets plus lag, rolling, temporal and route-wide features. Timetable
    facts are joined on when the static schedule has been loaded, and
    skipped otherwise so the realtime part can still be built.

    Args:
        None.

    Returns:
        None.
    """
    engine = get_engine()
    init_db(engine)

    dataset = build_features(engine, read_table(engine, "trip_updates"), read_table(engine, "vehicle_positions"))
    if dataset.empty:
        logger.warning("no trip updates stored yet, nothing to build")
        engine.dispose()
        return

    write_dataset(engine, dataset)
    logger.info(f"model_dataset: wrote {len(dataset)} rows, {dataset.shape[1]} columns")
    engine.dispose()


def build_features(engine, trip_updates_df: pd.DataFrame, vehicle_positions_df: pd.DataFrame) -> pd.DataFrame:
    """Turn raw feed rows into per-train, per-minute feature rows.

    Shared by build_dataset (all stored history, for training) and
    predict_live (the last few minutes), so a live prediction always sees
    features built exactly the way the model was trained on.

    Args:
        engine: SQLAlchemy engine, used to read the static schedule.
        trip_updates_df: Rows as stored in the trip_updates table.
        vehicle_positions_df: Rows as stored in the vehicle_positions table.

    Returns:
        Feature table with the model_dataset columns, or an empty frame
        when there are no usable trip updates.
    """
    delays = current_trip_delay(trip_updates_df)
    if delays.empty:
        return pd.DataFrame()

    windows = build_windows(delays, vehicle_positions_df)
    dataset = trip_delay_by_window(delays)
    dataset = add_trip_targets(dataset)
    dataset = add_lag_features(dataset)
    dataset = add_rolling_features(dataset)
    dataset = add_temporal_features(dataset)
    dataset = add_network_features(dataset, windows)
    logger.info(f"realtime features: {len(dataset)} rows across {dataset['trip_id'].nunique()} trips")

    if all(has_table(engine, name) for name in STATIC_TABLES):
        static = {name: read_table(engine, name) for name in STATIC_TABLES}
        match = match_trips(dataset, static["trips"], static["calendar"], static["calendar_dates"], static["stop_times"])
        schedule = stop_schedule(static["stop_times"], static["trips"])
        dataset = attach_timetable(dataset, match, static["trips"], static["stops"], schedule)
        logger.info(f"timetable join: {match['match_method'].value_counts().to_dict()}")
    else:
        logger.warning("static schedule not loaded, run --refresh-static to add timetable features")

    return dataset


def predict_live(engine, model_dir: Path = DEFAULT_MODEL_DIR, lookback_minutes: int = LIVE_LOOKBACK_MINUTES) -> pd.DataFrame:
    """Predict the 5, 10 and 15 minute delay for every train running right now.

    Only the last lookback_minutes of feed rows are read, which covers the
    15 minute rolling features while keeping each cycle to well under a second.

    Args:
        engine: SQLAlchemy engine.
        model_dir: Directory train.py saved the models into.
        lookback_minutes: How much recent history to build features from.

    Returns:
        One row per live train with its current delay and a predicted delay
        per horizon (all in seconds), as written to the predictions table.
        Empty when no train was seen recently.

    Raises:
        FileNotFoundError: If the models have not been trained yet.
    """
    since = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
    features = build_features(engine, read_recent(engine, "trip_updates", since), read_recent(engine, "vehicle_positions", since))
    if features.empty:
        return features

    features["window_start"] = pd.to_datetime(features["window_start"], utc=True)
    latest = features.sort_values("window_start").groupby("trip_id").tail(1)
    latest = latest[latest["window_start"] >= latest["window_start"].max() - timedelta(minutes=LIVE_MAX_AGE_MINUTES)]

    feature_columns = load_feature_columns(model_dir)
    out = latest.reindex(columns=[
        "trip_id", "route_id", "start_date", "trip_headsign", "window_start",
        "stop_id", "stop_name", "stop_sequence", "arrival_delay",
    ])
    for horizon in DEFAULT_HORIZONS_MINUTES:
        out[f"predicted_delay_{horizon}min"] = predict_delay(load_model(horizon, model_dir), latest, feature_columns)
    out["predicted_at"] = datetime.now(timezone.utc)
    return out.reset_index(drop=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Traffic analytics ingestion pipeline")
    parser.add_argument("--refresh-static", action="store_true", help="Download and store the static GTFS schedule instead of running a realtime cycle")
    parser.add_argument("--build-dataset", action="store_true", help="Build the model_dataset table from the stored feeds instead of running a realtime cycle")
    parser.add_argument("--publish", action="store_true", help="Also publish each decoded row to the Kafka broker during a realtime cycle")
    parser.add_argument("--predict", action="store_true", help="Also predict live delays from the saved models during a realtime cycle")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.refresh_static:
        refresh_static_gtfs()
    elif args.build_dataset:
        build_dataset()
    else:
        run_once(publish=args.publish, predict=args.predict)
