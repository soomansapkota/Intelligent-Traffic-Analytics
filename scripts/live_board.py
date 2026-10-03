"""Print a live departure board for one Sydney Metro station.

Fetches the trip updates feed right now and lists the next trains at the
station with scheduled time, expected time and delay -- the same view
TripView shows -- so the two can be compared side by side. Delays here come
straight from the TfNSW feed (arrival_delay, in seconds), not from
model_dataset or the API.

Needs the static tables loaded (`python -m src.orchestration.pipeline
--refresh-static`) for station names and destinations.

    python -m scripts.live_board --station Chatswood
    python -m scripts.live_board --station "Martin Place" --count 15
"""

import argparse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from src.ingestion.fetch_feeds import fetch_trip_updates
from src.processing.decode_feeds import decode_trip_updates
from src.storage.db import get_engine, read_table

SYDNEY = ZoneInfo("Australia/Sydney")


def format_delay(seconds: int) -> str:
    """Render a delay the way TripView does: 'on time', '2 min late', '1 min early'."""
    minutes = round(seconds / 60)
    if minutes == 0:
        return "on time"
    return f"{abs(minutes)} min {'late' if minutes > 0 else 'early'}"


def build_board(updates: pd.DataFrame, stops: pd.DataFrame, trips: pd.DataFrame, station: str, now_ts: int) -> pd.DataFrame:
    """Select the upcoming arrivals at a station from decoded trip updates.

    Args:
        updates: Output of decode_trip_updates.
        stops: The stops table.
        trips: The trips table, for each trip's destination.
        station: Case-insensitive substring of the station name.
        now_ts: Current time as epoch seconds; earlier arrivals are dropped.

    Returns:
        One row per upcoming arrival, soonest first.
    """
    matched = stops[stops["stop_name"].str.contains(station, case=False, na=False)]
    board = updates[
        updates["stop_id"].isin(matched["stop_id"])
        & (updates["arrival_time"] >= now_ts)
        & (updates["schedule_relationship"] != "SKIPPED")
    ]
    board = board.merge(matched[["stop_id", "stop_name"]], on="stop_id", how="left")
    board = board.merge(trips[["trip_id", "trip_headsign"]], on="trip_id", how="left")
    return board.sort_values("arrival_time")


def main() -> None:
    parser = argparse.ArgumentParser(description="Live departure board for one Metro station")
    parser.add_argument("--station", required=True, help='Station name or part of it, e.g. "Chatswood"')
    parser.add_argument("--count", type=int, default=10, help="Number of trains to show")
    args = parser.parse_args()

    engine = get_engine()
    stops, trips = read_table(engine, "stops"), read_table(engine, "trips")
    engine.dispose()
    if stops.empty:
        raise SystemExit("stops table is empty -- run `python -m src.orchestration.pipeline --refresh-static` first")

    now = datetime.now(timezone.utc)
    board = build_board(decode_trip_updates(fetch_trip_updates()), stops, trips, args.station, int(now.timestamp()))
    if board.empty:
        raise SystemExit(f'No upcoming trains found for "{args.station}"')

    def local(ts: int) -> str:
        return datetime.fromtimestamp(ts, SYDNEY).strftime("%H:%M")

    print(f"Live board fetched {now.astimezone(SYDNEY):%H:%M:%S} Sydney time\n")
    print(f"{'Sched':5}  {'Expect':6}  {'Delay':13}  {'Secs':>5}  {'To':12}  Platform")
    for row in board.head(args.count).itertuples():
        scheduled = row.arrival_time - row.arrival_delay
        platform = str(row.stop_name).split(",")[-1].strip()
        print(
            f"{local(scheduled):5}  {local(row.arrival_time):6}  {format_delay(row.arrival_delay):13}  "
            f"{row.arrival_delay:>5}  {str(row.trip_headsign or '?'):12}  {platform}"
        )


if __name__ == "__main__":
    main()
