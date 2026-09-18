import asyncio
import logging
import signal

import httpx2

from uptime_platform.core.config import (
    get_settings,
)
from uptime_platform.core.metrics import export_metrics, get_metrics
from uptime_platform.db.session import (
    SessionFactory,
)
from uptime_platform.notifications.worker import (
    NotificationWorker,
)

logger = logging.getLogger(__name__)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    settings = get_settings()

    logger.info("notification worker started")

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
            export_metrics(get_metrics("worker"), 9002),
            httpx2.AsyncClient() as client,
        ):
            worker = NotificationWorker(
                session_factory=SessionFactory,
                http_client=client,
                notification_timeout_seconds=(settings.notification_timeout_seconds),
            )

            await worker.run_forever()

    finally:
        loop.remove_signal_handler(signal.SIGTERM)


def run() -> None:
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("notification worker stopped")


if __name__ == "__main__":
    run()
