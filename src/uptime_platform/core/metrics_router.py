import asyncio

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from prometheus_client.core import GaugeMetricFamily
from sqlalchemy import func, select

from uptime_platform.core.metrics import get_metrics
from uptime_platform.db.session import SessionFactory
from uptime_platform.notifications.models import NotificationDeliveryModel
from uptime_platform.outbox.models import OutboxEventModel

router = APIRouter()
api_metrics = get_metrics("api")


async def notification_queue_size() -> tuple[int, int]:
    async with asyncio.timeout(5), SessionFactory() as session:
        result = await session.execute(
            select(
                select(func.count())
                .select_from(OutboxEventModel)
                .where(OutboxEventModel.processed_at.is_(None))
                .scalar_subquery(),
                select(func.count())
                .select_from(NotificationDeliveryModel)
                .where(NotificationDeliveryModel.processed_at.is_(None))
                .scalar_subquery(),
            )
        )
        return tuple(result.one())


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    fanout, deliveries = await notification_queue_size()
    queue = GaugeMetricFamily(
        "uptime_notification_queue_size",
        "Unprocessed outbox events and deliveries, including exhausted retries.",
        labels=["stage"],
    )
    queue.add_metric(["fanout"], fanout)
    queue.add_metric(["delivery"], deliveries)

    class QueueCollector:
        def collect(self):
            yield queue

    registry = CollectorRegistry()
    registry.register(QueueCollector())
    return Response(
        generate_latest(api_metrics.registry) + generate_latest(registry),
        headers={"Content-Type": CONTENT_TYPE_LATEST},
    )
