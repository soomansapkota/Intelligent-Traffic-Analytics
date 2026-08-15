import requests

from config.settings import ALERTS_URL, HEADERS, TRIP_UPDATES_URL, VEHICLE_POS_URL


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
