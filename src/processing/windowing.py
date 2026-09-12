import pandas as pd


def current_trip_delay(trip_updates: pd.DataFrame) -> pd.DataFrame:
    """Reduce raw trip_updates rows to one current delay reading per trip.

    A trip can appear multiple times in trip_updates (one row per stop, and
    possibly re-fetched across cycles) -- keep only the most recent reading
    per trip_id, e.g. by max(fetched_at).

    Args:
        trip_updates: Rows from the trip_updates table (or an equivalent
            in-memory frame), covering some recent time window.

    Returns:
        DataFrame with one row per trip_id: trip_id, route_id,
        arrival_delay (seconds, positive = late).
    """
    raise NotImplementedError


def build_windows(delays: pd.DataFrame, vehicles: pd.DataFrame, window_minutes: int = 1) -> pd.DataFrame:
    """Aggregate per-trip delay (and optionally vehicle speed) into fixed time windows.

    Bucket rows by flooring their timestamp to window_minutes, then group by
    (route_id, window) to summarize how delay is trending recently -- this is
    what StreamProcessor.current_windows() calls to build a rolling view over
    the last few minutes of streamed data.

    Args:
        delays: Output of current_trip_delay -- one row per trip.
        vehicles: Recent vehicle_positions rows, for a speed context per window.
        window_minutes: Width of each time bucket, in minutes.

    Returns:
        DataFrame with one row per (route_id, window): route_id, window_start,
        mean_delay_s, n_trips (suggested columns -- adjust as your analysis needs).
    """
    raise NotImplementedError
