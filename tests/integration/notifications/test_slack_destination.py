import json
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import httpx2
import pytest
from sqlalchemy import delete, select

from uptime_platform.notifications.entities import (
    NotificationDestination,
    NotificationDestinationType,
    SlackDestinationConfig,
)
from uptime_platform.notifications.models import NotificationDeliveryModel
from uptime_platform.notifications.sqlalchemy_repository import (
    SqlAlchemyNotificationDestinationRepository,
)
from uptime_platform.notifications.worker import NotificationWorker
from uptime_platform.organizations.models import OrganizationModel
from uptime_platform.outbox.entities import OutboxEventType
from uptime_platform.outbox.models import OutboxEventModel

pytestmark = pytest.mark.anyio
HOOK = "https://hooks.slack.com/services/T0123/B0456/secret-hook-value"


@pytest.fixture
async def destination(session_factory):
    now = datetime.now(UTC)
    destination = NotificationDestination(
        id=uuid4(),
        organization_id=uuid4(),
        name="Slack",
        destination_type=NotificationDestinationType.SLACK,
        enabled=True,
        config=SlackDestinationConfig(HOOK),
        created_at=now,
    )
    async with session_factory() as session, session.begin():
        session.add(
            OrganizationModel(
                id=destination.organization_id, name="Slack QA", created_at=now
            )
        )
        await session.flush()
        await SqlAlchemyNotificationDestinationRepository(session).create(destination)
    try:
        yield destination
    finally:
        async with session_factory() as session, session.begin():
            await session.execute(
                delete(OrganizationModel).where(
                    OrganizationModel.id == destination.organization_id
                )
            )


async def test_postgres_slack_roundtrip_rotation_and_tenant_isolation(
    session_factory, destination
):
    async with session_factory() as session, session.begin():
        repository = SqlAlchemyNotificationDestinationRepository(session)
        saved = await repository.get_by_id(destination.id, destination.organization_id)
        assert saved == destination
        assert saved.config.webhook_url == HOOK
        assert await repository.get_by_id(destination.id, uuid4()) is None
        assert await repository.get_all(uuid4()) == []
        assert await repository.delete(destination.id, uuid4()) is False
        rotated = replace(
            saved,
            config=SlackDestinationConfig(
                "https://hooks.slack-gov.com/services/T01/B02/rotated-secret"
            ),
        )
        await repository.update(rotated)
    async with session_factory() as session:
        saved = await SqlAlchemyNotificationDestinationRepository(session).get_by_id(
            destination.id, destination.organization_id
        )
        assert saved == rotated


async def test_postgres_slack_worker_retries_without_secret_error_and_sends_once_after_success(
    session_factory, destination
):
    now = datetime.now(UTC)
    event_id, monitor_id = uuid4(), uuid4()
    async with session_factory() as session, session.begin():
        session.add(
            OutboxEventModel(
                id=event_id,
                organization_id=destination.organization_id,
                event_type=OutboxEventType.INCIDENT_OPENED,
                payload={
                    "monitor_id": str(monitor_id),
                    "incident_id": str(uuid4()),
                    "monitor_name": "Production API",
                    "monitor_type": "http",
                    "target": "https://api.example.com/health",
                    "reason": "HTTP 503 Service Unavailable",
                    "started_at": now.isoformat(),
                },
                created_at=now,
                processed_at=None,
            )
        )
        await SqlAlchemyNotificationDestinationRepository(session).create(
            replace(destination, id=uuid4(), enabled=False, name="Disabled Slack")
        )
    requests = []

    def handler(request):
        requests.append(request)
        return (
            httpx2.Response(429, text=f"rate_limited {HOOK}")
            if len(requests) == 1
            else httpx2.Response(200, text="ok")
        )

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        worker = NotificationWorker(
            session_factory, client, public_app_url="https://uptime.example.com"
        )
        await worker.run_once()
        async with session_factory() as session, session.begin():
            deliveries = (
                await session.scalars(
                    select(NotificationDeliveryModel).where(
                        NotificationDeliveryModel.event_id == event_id
                    )
                )
            ).all()
            assert len(deliveries) == 1
            delivery = deliveries[0]
            assert delivery.destination_id == destination.id
            assert delivery.attempts == 1
            assert delivery.processed_at is None
            assert delivery.locked_until is None
            assert delivery.lease_token is None
            assert delivery.last_error and "Slack" in delivery.last_error
            assert "secret-hook-value" not in delivery.last_error
            assert "hooks.slack.com" not in delivery.last_error
            delivery.next_attempt_at = datetime.now(UTC)
        await worker.run_once()
        await worker.run_once()
    assert len(requests) == 2
    assert requests[0].content == requests[1].content
    assert str(requests[0].url) == HOOK
    body = json.loads(requests[0].content)
    assert "Production API" in body["text"]
    assert f"https://uptime.example.com/monitors/{monitor_id}" in body["text"]
    async with session_factory() as session:
        delivery = await session.scalar(
            select(NotificationDeliveryModel).where(
                NotificationDeliveryModel.event_id == event_id
            )
        )
        assert delivery.attempts == 2
        assert delivery.processed_at is not None
        assert delivery.last_error is None
        assert delivery.lease_token is None
