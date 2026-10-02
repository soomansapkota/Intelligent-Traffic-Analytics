import argparse
import logging
import time

from src.orchestration.pipeline import run_once

logger = logging.getLogger(__name__)


def run_forever(interval_seconds: int = 30, publish: bool = False, duration_minutes: float | None = None) -> None:
    """Run the pipeline again and again, waiting between each run.

    Args:
        interval_seconds: Seconds to wait between runs. Minimum 15, so we
            do not poll the API faster than TfNSW updates its feeds.
        publish: Also publish each cycle's rows to the Kafka broker.
        duration_minutes: Stop after roughly this long, or run until
            interrupted when left as None. One cycle always runs.

    Returns:
        None.
    """
    interval_seconds = max(interval_seconds, 15)
    deadline = time.monotonic() + duration_minutes * 60 if duration_minutes is not None else None
    logger.info(f"starting scheduler, interval={interval_seconds}s publish={publish} duration={duration_minutes}")

    cycles = 0
    try:
        while True:
            run_once(publish=publish)
            cycles += 1
            if deadline is not None and time.monotonic() >= deadline:
                break
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        logger.info("scheduler interrupted")
    logger.info(f"scheduler stopped after {cycles} cycles")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Poll the TfNSW feeds on a fixed interval")
    parser.add_argument("--interval", type=int, default=30, help="Seconds between polls, minimum 15")
    parser.add_argument("--minutes", type=float, default=None, help="Stop after this many minutes instead of running until interrupted")
    parser.add_argument("--publish", action="store_true", help="Also publish each cycle's rows to the Kafka broker")
    args = parser.parse_args()
    run_forever(interval_seconds=args.interval, publish=args.publish, duration_minutes=args.minutes)
