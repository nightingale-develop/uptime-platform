import asyncio
import logging
import signal

from uptime_platform.core.config import get_settings
from uptime_platform.core.metrics import export_metrics, get_metrics
from uptime_platform.db.session import (
    SessionFactory,
)
from uptime_platform.retention.service import RetentionService
from uptime_platform.scheduler.scheduler import (
    Scheduler,
)

logger = logging.getLogger(__name__)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    logger.info("scheduler started")

    scheduler = Scheduler(
        session_factory=SessionFactory,
    )

    loop = asyncio.get_running_loop()
    task = asyncio.current_task()
    stopping = False

    def stop() -> None:
        nonlocal stopping
        if not stopping and task is not None:
            stopping = True
            task.cancel()

    loop.add_signal_handler(signal.SIGTERM, stop)
    try:
        async with (
            export_metrics(get_metrics("scheduler"), 9001),
            asyncio.TaskGroup() as group,
        ):
            group.create_task(
                RetentionService(SessionFactory, get_settings()).run_forever()
            )
            group.create_task(scheduler.run_forever())
    finally:
        loop.remove_signal_handler(signal.SIGTERM)


def run() -> None:
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("scheduler stopped")


if __name__ == "__main__":
    run()
