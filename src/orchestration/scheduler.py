import logging
import time

from src.orchestration.pipeline import run_once

logger = logging.getLogger(__name__)


def run_forever(interval_seconds: int = 30) -> None:
    """Run the pipeline again and again, waiting between each run.

    Args:
        interval_seconds: Seconds to wait between runs. Minimum 15, so we
            do not poll the API faster than TfNSW updates its feeds.

    Returns:
        None.
    """
    interval_seconds = max(interval_seconds, 15)
    logger.info(f"starting scheduler, interval={interval_seconds}s")
    try:
        while True:
            run_once()
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        logger.info("scheduler stopped")


if __name__ == "__main__":
    run_forever()
