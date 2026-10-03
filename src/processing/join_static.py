import pandas as pd

# TfNSW metro trip_ids look like 0241-001-101-016:1000. The leading two
# segments change with every timetable revision, so realtime and static
# ids rarely match exactly. The run and trip number (101-016) survives
# revisions and identifies the physical service, so it is the join key.
RUN_KEY_PATTERN = r"^\d+-\d+-(\d+-\d+):"

WEEKDAY_COLUMNS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def run_key(trip_ids: pd.Series) -> pd.Series:
    """Extract the revision-independent run and trip number from trip_ids.

    Args:
        trip_ids: Series of TfNSW trip_id strings.

    Returns:
        Series of "run-trip" keys, null where the id does not fit the pattern.
    """
    return trip_ids.str.extract(RUN_KEY_PATTERN)[0]


def gtfs_time_to_seconds(times: pd.Series) -> pd.Series:
    """Convert GTFS HH:MM:SS strings to seconds past service-day midnight.

    Hours may exceed 23 for services running past midnight, which is why
    this is not parsed as a time of day.

    Args:
        times: Series of HH:MM:SS strings.

    Returns:
        Series of integer seconds.
    """
    parts = times.str.split(":", expand=True).astype("int64")
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def services_on_date(calendar_df: pd.DataFrame, calendar_dates_df: pd.DataFrame, date: str) -> set[str]:
    """Resolve which service_ids run on a given service day.

    Args:
        calendar_df: Static calendar table, one row per service_id.
        calendar_dates_df: Static calendar_dates table of exceptions.
        date: Service day as YYYYMMDD.

    Returns:
        Set of service_ids active on that date.
    """
    active: set[str] = set()
    if not calendar_df.empty:
        weekday = WEEKDAY_COLUMNS[pd.Timestamp(date).dayofweek]
        in_range = (calendar_df["start_date"] <= date) & (calendar_df["end_date"] >= date)
        active = set(calendar_df.loc[in_range & (calendar_df[weekday] == "1"), "service_id"])
    if not calendar_dates_df.empty:
        on_date = calendar_dates_df[calendar_dates_df["date"] == date]
        active |= set(on_date.loc[on_date["exception_type"] == "1", "service_id"])
        active -= set(on_date.loc[on_date["exception_type"] == "2", "service_id"])
    return active


def match_trips(
    realtime_df: pd.DataFrame,
    trips_df: pd.DataFrame,
    calendar_df: pd.DataFrame,
    calendar_dates_df: pd.DataFrame,
    stop_times_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Map each realtime (trip_id, start_date) to a single static trip_id.

    An exact trip_id match is used when the timetable revisions line up.
    Otherwise candidates share the run key, and the calendar picks the one
    whose service runs on start_date. If the calendar cannot narrow it to
    one, the candidate covering the most stops the realtime trip was seen
    at is preferred, then the lowest trip_id so the choice is deterministic.
    match_method records which path was taken.

    Args:
        realtime_df: Any frame with trip_id and start_date columns. A stop_id
            column, if present, is used to break ties between candidates.
        trips_df: Static trips table.
        calendar_df: Static calendar table.
        calendar_dates_df: Static calendar_dates table.
        stop_times_df: Static stop_times table, needed for the stop tie-break.

    Returns:
        DataFrame with trip_id, start_date, static_trip_id and match_method,
        one row per distinct realtime (trip_id, start_date).
    """
    wanted = realtime_df[["trip_id", "start_date"]].drop_duplicates().reset_index(drop=True)
    static = trips_df[["trip_id", "service_id"]].assign(run_key=run_key(trips_df["trip_id"]))
    static_ids = set(static["trip_id"])
    by_run_key = static.groupby("run_key")

    observed_stops: dict = {}
    static_stops: dict = {}
    if stop_times_df is not None and "stop_id" in realtime_df.columns:
        seen = realtime_df.assign(stop_id=realtime_df["stop_id"].astype(str))
        observed_stops = seen.groupby(["trip_id", "start_date"])["stop_id"].apply(set).to_dict()
        timetable = stop_times_df.assign(stop_id=stop_times_df["stop_id"].astype(str))
        static_stops = timetable.groupby("trip_id")["stop_id"].apply(set).to_dict()

    def pick(candidates: pd.DataFrame, trip_id: str, start_date: str) -> str:
        seen_here = observed_stops.get((trip_id, start_date))
        if seen_here and static_stops:
            overlap = candidates["trip_id"].map(lambda t: len(seen_here & static_stops.get(t, set())))
            candidates = candidates[overlap == overlap.max()]
        return candidates["trip_id"].min()

    rows = []
    for trip_id, start_date in wanted.itertuples(index=False):
        if trip_id in static_ids:
            rows.append((trip_id, start_date, trip_id, "exact"))
            continue

        key = run_key(pd.Series([trip_id])).iloc[0]
        if pd.isna(key) or key not in by_run_key.groups:
            rows.append((trip_id, start_date, None, "unmatched"))
            continue

        candidates = by_run_key.get_group(key)
        active = services_on_date(calendar_df, calendar_dates_df, start_date)
        in_service = candidates[candidates["service_id"].isin(active)]
        if len(in_service) == 1:
            rows.append((trip_id, start_date, in_service["trip_id"].iloc[0], "run_key_calendar"))
        elif len(in_service) > 1:
            rows.append((trip_id, start_date, pick(in_service, trip_id, start_date), "run_key_ambiguous"))
        else:
            rows.append((trip_id, start_date, pick(candidates, trip_id, start_date), "run_key_no_calendar"))

    return pd.DataFrame(rows, columns=["trip_id", "start_date", "static_trip_id", "match_method"])


def stop_schedule(stop_times_df: pd.DataFrame, trips_df: pd.DataFrame) -> pd.DataFrame:
    """Derive per-stop timetable facts for every static trip.

    Args:
        stop_times_df: Static stop_times table.
        trips_df: Static trips table, for direction_id.

    Returns:
        DataFrame keyed by (trip_id, stop_id) with the stop's position in
        the trip, the fraction of the trip completed on reaching it, the
        scheduled arrival in seconds, the scheduled run time from the
        previous stop, and the scheduled headway behind the previous service
        at that stop in the same direction and on the same day-type
        timetable.
    """
    st = stop_times_df[["trip_id", "stop_id", "stop_sequence", "arrival_time"]].copy()
    st["stop_sequence"] = st["stop_sequence"].astype("int64")
    st["sched_arrival_secs"] = gtfs_time_to_seconds(st["arrival_time"])
    st = st.merge(trips_df[["trip_id", "service_id", "direction_id"]], on="trip_id", how="left")
    st = st.sort_values(["trip_id", "stop_sequence"])

    by_trip = st.groupby("trip_id")
    st["stop_position"] = by_trip.cumcount() + 1
    st["n_stops_in_trip"] = by_trip["stop_id"].transform("size")
    st["frac_trip_complete"] = st["stop_position"] / st["n_stops_in_trip"]
    st["sched_run_secs_from_prev"] = by_trip["sched_arrival_secs"].diff()

    # Each service_id is a complete day-type timetable, so headway is measured inside one to avoid zero gaps between copies.
    st = st.sort_values(["service_id", "stop_id", "direction_id", "sched_arrival_secs"])
    st["sched_headway_secs"] = st.groupby(["service_id", "stop_id", "direction_id"])["sched_arrival_secs"].diff()

    columns = [
        "trip_id", "service_id", "stop_id", "direction_id", "stop_position", "n_stops_in_trip",
        "frac_trip_complete", "sched_arrival_secs", "sched_run_secs_from_prev", "sched_headway_secs",
    ]
    return st[columns].reset_index(drop=True)


def attach_timetable(
    df: pd.DataFrame,
    match_df: pd.DataFrame,
    trips_df: pd.DataFrame,
    stops_df: pd.DataFrame,
    schedule_df: pd.DataFrame,
) -> pd.DataFrame:
    """Join static trip, stop and schedule facts onto realtime rows.

    Args:
        df: Realtime rows with trip_id, start_date and stop_id.
        match_df: Output of match_trips.
        trips_df: Static trips table.
        stops_df: Static stops table.
        schedule_df: Output of stop_schedule.

    Returns:
        df with static_trip_id, match_method, direction_id, trip_headsign,
        stop_name, stop_lat, stop_lon and every stop_schedule column.
    """
    out = df.copy()
    out["stop_id"] = out["stop_id"].astype(str)
    out = out.merge(match_df, on=["trip_id", "start_date"], how="left")

    trip_info = trips_df[["trip_id", "trip_headsign"]].rename(columns={"trip_id": "static_trip_id"})
    out = out.merge(trip_info, on="static_trip_id", how="left")

    stop_info = stops_df[["stop_id", "stop_name", "stop_lat", "stop_lon"]].copy()
    stop_info["stop_id"] = stop_info["stop_id"].astype(str)
    stop_info[["stop_lat", "stop_lon"]] = stop_info[["stop_lat", "stop_lon"]].astype(float)
    out = out.merge(stop_info, on="stop_id", how="left")

    schedule = schedule_df.rename(columns={"trip_id": "static_trip_id"})
    schedule["stop_id"] = schedule["stop_id"].astype(str)
    return out.merge(schedule, on=["static_trip_id", "stop_id"], how="left")
