"""Timetable lookups for the journey planner.

Works on the static GTFS tables as stored (every column text) and knows
nothing about the database or the API, so it can be tested on small
hand-built frames. Stations are stop names with the platform dropped:
"Chatswood Station, Platform 2" and "..., Platform 3" are one station.
"""

import pandas as pd

from src.processing.join_static import gtfs_time_to_seconds, services_on_date

DAY_SECONDS = 24 * 3600


def station_names(stop_names: pd.Series) -> pd.Series:
    """Drop the platform from stop names: "Chatswood Station, Platform 2" -> "Chatswood Station"."""
    return stop_names.str.split(",").str[0].str.strip()


def line_stations(stops_df: pd.DataFrame, trips_df: pd.DataFrame, stop_times_df: pd.DataFrame) -> list[str]:
    """Station names in running order along the line.

    Taken from the trip calling at the most stops in direction 1
    (Tallawong to Sydenham), so short-running trips do not cut the list.

    Args:
        stops_df: Static stops table.
        trips_df: Static trips table.
        stop_times_df: Static stop_times table.

    Returns:
        Station names, first to last stop, without duplicates.
    """
    direction = trips_df.loc[trips_df["direction_id"] == "1", "trip_id"]
    calls = stop_times_df[stop_times_df["trip_id"].isin(direction)]
    if calls.empty:
        calls = stop_times_df
    longest = calls.groupby("trip_id").size().idxmax()
    trip = calls[calls["trip_id"] == longest].copy()
    trip["seq"] = trip["stop_sequence"].astype(int)
    names = station_names(trip.sort_values("seq")["stop_id"].map(stops_df.set_index("stop_id")["stop_name"]))
    return list(dict.fromkeys(names.dropna()))


def next_departures(
    from_station: str,
    to_station: str,
    now: pd.Timestamp,
    stops_df: pd.DataFrame,
    trips_df: pd.DataFrame,
    stop_times_df: pd.DataFrame,
    calendar_df: pd.DataFrame,
    calendar_dates_df: pd.DataFrame,
    limit: int = 5,
    grace_minutes: int = 2,
) -> pd.DataFrame:
    """The next scheduled trains calling at from_station and then at to_station.

    Yesterday's service day is checked as well as today's, because GTFS
    writes trains after midnight as e.g. 24:15:00 on the previous day.
    Trains scheduled up to grace_minutes ago are kept, since a late train
    may not have left yet; the caller drops those that live data shows
    have gone.

    Args:
        from_station: Station name as returned by line_stations.
        to_station: Station name as returned by line_stations.
        now: Current time, timezone-aware in Australia/Sydney.
        stops_df, trips_df, stop_times_df, calendar_df, calendar_dates_df:
            Static GTFS tables as stored.
        limit: Maximum number of departures to return.
        grace_minutes: How far back to include scheduled departures.

    Returns:
        One row per departure, soonest first: trip_id (static), service_date
        (YYYYMMDD), trip_headsign, origin_stop_sequence, and departure and
        arrival as seconds past today's midnight (negative or past 86,400
        for trains belonging to yesterday's or running into tomorrow's day).
    """
    columns = ["trip_id", "service_date", "trip_headsign", "origin_stop_sequence", "departure_seconds", "arrival_seconds"]
    calls = stop_times_df.merge(stops_df[["stop_id", "stop_name"]], on="stop_id", how="left")
    calls["station"] = station_names(calls["stop_name"])
    calls["seq"] = calls["stop_sequence"].astype(int)

    origin = calls[calls["station"] == from_station]
    origin = origin.assign(departure=gtfs_time_to_seconds(origin["departure_time"]))[["trip_id", "seq", "departure"]]
    dest = calls[calls["station"] == to_station]
    dest = dest.assign(arrival=gtfs_time_to_seconds(dest["arrival_time"]))[["trip_id", "seq", "arrival"]]
    pairs = origin.merge(dest, on="trip_id", suffixes=("_origin", "_dest"))
    pairs = pairs[pairs["seq_origin"] < pairs["seq_dest"]]  # right direction only
    pairs = pairs.merge(trips_df[["trip_id", "service_id", "trip_headsign"]], on="trip_id")

    today = now.normalize()
    now_seconds = (now - today).total_seconds()
    parts = []
    for days_back in (1, 0):
        service_date = (today - pd.Timedelta(days=days_back)).strftime("%Y%m%d")
        running = pairs[pairs["service_id"].isin(services_on_date(calendar_df, calendar_dates_df, service_date))]
        offset = -days_back * DAY_SECONDS
        parts.append(pd.DataFrame({
            "trip_id": running["trip_id"],
            "service_date": service_date,
            "trip_headsign": running["trip_headsign"],
            "origin_stop_sequence": running["seq_origin"],
            "departure_seconds": running["departure"] + offset,
            "arrival_seconds": running["arrival"] + offset,
        }))
    departures = pd.concat(parts, ignore_index=True)
    departures = departures[departures["departure_seconds"] >= now_seconds - grace_minutes * 60]
    return departures.sort_values("departure_seconds").head(limit).reset_index(drop=True)[columns]


def live_only_departures(
    stop_rows: pd.DataFrame,
    stops_df: pd.DataFrame,
    from_station: str,
    to_station: str,
    today: pd.Timestamp,
) -> pd.DataFrame:
    """Departures for live trains that are not in the published timetable.

    TfNSW runs extra trains (trip ids like "M1-I-CUD_UP-SYD_UP-...:X") that
    no static trip matches. Their own trip update still lists a time and a
    delay for every stop, so the feed's schedule -- time minus delay -- stands
    in for the timetable's, keeping the result comparable with next_departures.

    Args:
        stop_rows: Each train's latest trip update rows: trip_id, start_date,
            stop_id, stop_sequence, arrival_time and departure_time (Unix
            seconds) and arrival_delay (seconds).
        stops_df: Static stops table, for station names.
        from_station: Station name as returned by line_stations.
        to_station: Station name as returned by line_stations.
        today: Midnight starting today in Australia/Sydney.

    Returns:
        The same columns as next_departures, unsorted and unlimited, with the
        destination taken from each train's last listed stop.
    """
    columns = ["trip_id", "service_date", "trip_headsign", "origin_stop_sequence", "departure_seconds", "arrival_seconds"]
    if stop_rows.empty:
        return pd.DataFrame(columns=columns)

    rows = stop_rows.merge(stops_df[["stop_id", "stop_name"]], on="stop_id", how="left")
    rows["station"] = station_names(rows["stop_name"])
    rows["seq"] = rows["stop_sequence"].astype(int)
    # A zero time means "not given" (the first stop often has no arrival).
    arrival = rows["arrival_time"].where(rows["arrival_time"] > 0)
    departure = rows["departure_time"].where(rows["departure_time"] > 0).fillna(arrival)
    delay = rows["arrival_delay"].fillna(0)
    midnight = today.timestamp()
    rows["scheduled_departure"] = departure - delay - midnight
    rows["scheduled_arrival"] = arrival - delay - midnight

    last_station = rows.sort_values("seq").groupby("trip_id")["station"].last()
    origin = rows[rows["station"] == from_station].dropna(subset=["scheduled_departure"])
    dest = rows[rows["station"] == to_station].dropna(subset=["scheduled_arrival"])
    pairs = origin[["trip_id", "start_date", "seq", "scheduled_departure"]].merge(
        dest[["trip_id", "seq", "scheduled_arrival"]], on="trip_id", suffixes=("_origin", "_dest"),
    )
    pairs = pairs[pairs["seq_origin"] < pairs["seq_dest"]]
    return pd.DataFrame({
        "trip_id": pairs["trip_id"],
        "service_date": pairs["start_date"],
        "trip_headsign": pairs["trip_id"].map(last_station).str.removesuffix(" Station"),
        "origin_stop_sequence": pairs["seq_origin"],
        "departure_seconds": pairs["scheduled_departure"],
        "arrival_seconds": pairs["scheduled_arrival"],
    }).reset_index(drop=True)[columns]


def delay_at_station(stop_rows: pd.DataFrame, stops_df: pd.DataFrame, station: str) -> pd.Series:
    """TfNSW's forecast delay at one station, per train, from the live trip updates.

    Every trip update lists a delay for each stop still ahead, so this covers
    trains that have not started their trip yet and so have no measured
    delay for the model to work from.

    Args:
        stop_rows: Latest trip update rows: trip_id, stop_id, arrival_delay (seconds).
        stops_df: Static stops table, for station names.
        station: Station name as returned by line_stations.

    Returns:
        Delay in seconds, indexed by realtime trip_id; trains not listing
        the station are absent.
    """
    if stop_rows.empty:
        return pd.Series(dtype=float)
    names = stop_rows["stop_id"].map(stops_df.set_index("stop_id")["stop_name"])
    at = stop_rows[(station_names(names) == station) & stop_rows["arrival_delay"].notna()]
    return at.drop_duplicates("trip_id").set_index("trip_id")["arrival_delay"].astype(float)


def clock(seconds: float) -> str:
    """Seconds past today's midnight as a 24-hour HH:MM clock time."""
    minutes = int(round(seconds / 60)) % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def nearest_horizon(minutes_ahead: float, horizons: tuple[int, ...] = (5, 10, 15)) -> int:
    """The prediction horizon closest to how far away the departure is."""
    return min(horizons, key=lambda h: abs(h - minutes_ahead))
