from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, update

from uptime_platform.core import metrics_router
from uptime_platform.notifications.entities import NotificationDestinationType
from uptime_platform.notifications.models import (
    NotificationDeliveryModel,
    NotificationDestinationModel,
)
from uptime_platform.organizations.models import OrganizationModel
from uptime_platform.outbox.entities import OutboxEventType
from uptime_platform.outbox.models import OutboxEventModel

pytestmark = pytest.mark.anyio


async def test_queue_counts_committed_backlog_including_leases_retries_and_exhausted(
    session_factory, monkeypatch
):
    monkeypatch.setattr(metrics_router, "SessionFactory", session_factory)
    baseline = await metrics_router.notification_queue_size()
    now = datetime.now(UTC)
    organization_id, destination_id = uuid4(), uuid4()
    events = [uuid4() for _ in range(5)]
    try:
        async with session_factory() as session, session.begin():
            session.add(
                OrganizationModel(
                    id=organization_id, name="Metrics test", created_at=now
                )
            )
            await session.flush()
            session.add(
                NotificationDestinationModel(
                    id=destination_id,
                    organization_id=organization_id,
                    name="Metrics destination",
                    destination_type=NotificationDestinationType.WEBHOOK,
                    enabled=True,
                    config={"url": "https://example.com", "secret": "test"},
                    created_at=now,
                )
            )
            session.add_all(
                [
                    OutboxEventModel(
                        id=event_id,
                        organization_id=organization_id,
                        event_type=OutboxEventType.INCIDENT_OPENED,
                        payload={},
                        created_at=now,
                        processed_at=None if index == 0 else now,
                    )
                    for index, event_id in enumerate(events)
                ]
            )
            await session.flush()
            session.add_all(
                [
                    NotificationDeliveryModel(
                        id=uuid4(),
                        event_id=event_id,
                        destination_id=destination_id,
                        created_at=now,
                        processed_at=now if index == 4 else None,
                        attempts=5 if index == 3 else 0,
                        last_error=None,
                        next_attempt_at=now + timedelta(hours=1) if index == 2 else now,
                        locked_until=now + timedelta(minutes=1) if index == 1 else None,
                    )
                    for index, event_id in enumerate(events)
                ]
            )
        assert await metrics_router.notification_queue_size() == (
            baseline[0] + 1,
            baseline[1] + 4,
        )
        async with session_factory() as session, session.begin():
            await session.execute(
                update(NotificationDeliveryModel)
                .where(NotificationDeliveryModel.destination_id == destination_id)
                .values(processed_at=now)
            )
            await session.execute(
                update(OutboxEventModel)
                .where(OutboxEventModel.organization_id == organization_id)
                .values(processed_at=now)
            )
        assert await metrics_router.notification_queue_size() == baseline
    finally:
        async with session_factory() as session, session.begin():
            await session.execute(
                delete(OrganizationModel).where(OrganizationModel.id == organization_id)
            )
