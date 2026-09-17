from datetime import UTC, datetime
from uuid import uuid4

import pytest

from uptime_platform.notifications.entities import (
    NotificationDelivery,
)
from uptime_platform.notifications.exceptions import (
    NotificationDeliveryError,
)
from uptime_platform.notifications.service import (
    NotificationService,
)
from uptime_platform.organizations.constants import DEFAULT_ORGANIZATION_ID
from uptime_platform.outbox.entities import (
    OutboxEvent,
    OutboxEventType,
)

pytestmark = pytest.mark.anyio


class StubNotificationChannel:
    async def send(
        self,
        event: OutboxEvent,
    ) -> None:
        pass


class FailingNotificationChannel:
    async def send(
        self,
        event: OutboxEvent,
    ) -> None:
        raise NotificationDeliveryError("Notification failed")


def make_event() -> OutboxEvent:
    now = datetime.now(UTC)

    return OutboxEvent(
        id=uuid4(),
        organization_id=DEFAULT_ORGANIZATION_ID,
        event_type=OutboxEventType.INCIDENT_OPENED,
        payload={
            "incident_id": str(uuid4()),
            "monitor_id": str(uuid4()),
        },
        created_at=now,
        processed_at=None,
    )


def make_delivery(
    event: OutboxEvent,
    attempts: int = 0,
) -> NotificationDelivery:
    now = datetime.now(UTC)

    return NotificationDelivery(
        id=uuid4(),
        event_id=event.id,
        destination_id=uuid4(),
        created_at=now,
        processed_at=None,
        attempts=attempts,
        last_error=None,
        next_attempt_at=now,
        locked_until=now,
    )


async def test_successful_notification_marks_delivery_processed() -> None:
    event = make_event()
    delivery = make_delivery(event)

    service = NotificationService()

    result = await service.process(
        delivery=delivery,
        event=event,
        channel=StubNotificationChannel(),
    )

    assert result.processed_at is not None
    assert result.attempts == 1
    assert result.last_error is None
    assert result.locked_until is None


async def test_failed_notification_schedules_retry() -> None:
    event = make_event()
    delivery = make_delivery(event)

    service = NotificationService()

    result = await service.process(
        delivery=delivery,
        event=event,
        channel=FailingNotificationChannel(),
    )

    assert result.processed_at is None
    assert result.attempts == 1
    assert result.last_error == ("Notification failed")
    assert result.next_attempt_at > delivery.next_attempt_at
    assert result.locked_until is None


async def test_retry_increments_existing_attempt_count() -> None:
    event = make_event()

    delivery = make_delivery(
        event,
        attempts=2,
    )

    service = NotificationService()

    result = await service.process(
        delivery=delivery,
        event=event,
        channel=FailingNotificationChannel(),
    )

    assert result.attempts == 3


async def test_delivery_metrics_count_retry_and_success_once():
    from uptime_platform.core.metrics import Metrics

    metrics = Metrics("worker")
    service = NotificationService(metrics=metrics)
    event = make_event()
    failed = await service.process(
        make_delivery(event), event, FailingNotificationChannel()
    )
    successful = await service.process(failed, event, StubNotificationChannel())
    assert successful.attempts == 2
    assert (
        metrics.registry.get_sample_value(
            "uptime_notification_deliveries_total", {"outcome": "failure"}
        )
        == 1
    )
    assert (
        metrics.registry.get_sample_value(
            "uptime_notification_deliveries_total", {"outcome": "success"}
        )
        == 1
    )


async def test_unexpected_delivery_error_is_counted_and_propagated():
    from unittest.mock import AsyncMock

    from uptime_platform.core.metrics import Metrics

    metrics = Metrics("worker")
    service = NotificationService(metrics=metrics)
    event = make_event()
    channel = StubNotificationChannel()
    channel.send = AsyncMock(side_effect=RuntimeError("unexpected"))
    with pytest.raises(RuntimeError):
        await service.process(make_delivery(event), event, channel)
    assert (
        metrics.registry.get_sample_value(
            "uptime_notification_deliveries_total", {"outcome": "failure"}
        )
        == 1
    )
