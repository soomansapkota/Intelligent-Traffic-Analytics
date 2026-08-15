import pandas as pd
from google.transit import gtfs_realtime_pb2


def decode_trip_updates(raw_bytes: bytes) -> pd.DataFrame:
    """Decode the trip updates feed into a flat table, one row per stop.

    Args:
        raw_bytes: Raw protobuf bytes from the trip updates feed.

    Returns:
        DataFrame with one row per stop time update.
    """
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(raw_bytes)

    rows = []
    for entity in feed.entity:
        tu = entity.trip_update
        for stu in tu.stop_time_update:
            rows.append({
                "entity_id": entity.id,
                "trip_id": tu.trip.trip_id,
                "route_id": tu.trip.route_id,
                "start_date": tu.trip.start_date,
                "stop_sequence": stu.stop_sequence,
                "stop_id": stu.stop_id,
                "arrival_time": stu.arrival.time,
                "arrival_delay": stu.arrival.delay,
                "departure_time": stu.departure.time,
                "schedule_relationship": gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.ScheduleRelationship.Name(stu.schedule_relationship),
            })

    return pd.DataFrame(rows)


def decode_vehicle_positions(raw_bytes: bytes) -> pd.DataFrame:
    """Decode the vehicle positions feed into a flat table, one row per vehicle.

    Args:
        raw_bytes: Raw protobuf bytes from the vehicle positions feed.

    Returns:
        DataFrame with one row per vehicle.
    """
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(raw_bytes)

    rows = []
    for entity in feed.entity:
        v = entity.vehicle
        rows.append({
            "entity_id": entity.id,
            "trip_id": v.trip.trip_id,
            "route_id": v.trip.route_id,
            "vehicle_id": v.vehicle.id or entity.id,
            "vehicle_label": v.vehicle.label,
            "lat": v.position.latitude,
            "lon": v.position.longitude,
            "bearing": v.position.bearing,
            "speed": v.position.speed,
            "current_stop_sequence": v.current_stop_sequence,
            "current_status": gtfs_realtime_pb2.VehiclePosition.VehicleStopStatus.Name(v.current_status),
            "timestamp": v.timestamp,
            "occupancy_status": gtfs_realtime_pb2.VehiclePosition.OccupancyStatus.Name(v.occupancy_status) if v.HasField("occupancy_status") else None,
        })

    return pd.DataFrame(rows)


def decode_alerts(raw_bytes: bytes) -> pd.DataFrame:
    """Decode the alerts feed into a flat table, one row per affected route.

    Args:
        raw_bytes: Raw protobuf bytes from the alerts feed.

    Returns:
        DataFrame with one row per (alert, affected route) pair.
    """
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(raw_bytes)

    rows = []
    for entity in feed.entity:
        a = entity.alert
        header = a.header_text.translation[0].text if a.header_text.translation else None
        description = a.description_text.translation[0].text if a.description_text.translation else None
        route_ids = [ie.route_id for ie in a.informed_entity if ie.route_id] or [None]
        for route_id in route_ids:
            rows.append({
                "entity_id": entity.id,
                "cause": gtfs_realtime_pb2.Alert.Cause.Name(a.cause),
                "effect": gtfs_realtime_pb2.Alert.Effect.Name(a.effect),
                "header_text": header,
                "description_text": description,
                "route_id": route_id,
            })

    return pd.DataFrame(rows)
