import requests

from config.settings import ALERTS_URL, HEADERS, STATIC_GTFS_URL, TRIP_UPDATES_URL, VEHICLE_POS_URL


def fetch_trip_updates() -> bytes:
    """Fetch the trip updates feed.

    Args:
        None.

    Returns:
        Raw protobuf bytes from the trip updates feed.
    """
    resp = requests.get(TRIP_UPDATES_URL, headers=HEADERS)
    resp.raise_for_status()
    return resp.content


def fetch_vehicle_positions() -> bytes:
    """Fetch the vehicle positions feed.

    Args:
        None.

    Returns:
        Raw protobuf bytes from the vehicle positions feed.
    """
    resp = requests.get(VEHICLE_POS_URL, headers=HEADERS)
    resp.raise_for_status()
    return resp.content


def fetch_alerts() -> bytes:
    """Fetch the service alerts feed.

    Args:
        None.

    Returns:
        Raw protobuf bytes from the alerts feed.
    """
    resp = requests.get(ALERTS_URL, headers=HEADERS)
    resp.raise_for_status()
    return resp.content


def fetch_static_gtfs() -> bytes:
    """Fetch the combined NSW static GTFS schedule (routes/trips/stops/stop_times).

    This covers every operator in NSW, not just Sydney Metro; callers should
    filter it down (see src.processing.decode_feeds.decode_static_gtfs).

    Args:
        None.

    Returns:
        Raw bytes of the static GTFS zip file.
    """
    resp = requests.get(STATIC_GTFS_URL, headers=HEADERS, timeout=180)
    resp.raise_for_status()
    return resp.content
