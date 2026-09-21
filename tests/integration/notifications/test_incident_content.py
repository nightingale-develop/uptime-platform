import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import httpx2
import pytest
from sqlalchemy import delete, select, update

from uptime_platform.checks.entities import CheckResult
from uptime_platform.checks.factory import CheckerFactory
from uptime_platform.checks.models import CheckModel
from uptime_platform.checks.service import CheckService
from uptime_platform.checks.sqlalchemy_repository import SqlAlchemyCheckRepository
from uptime_platform.incidents.models import IncidentModel
from uptime_platform.incidents.sqlalchemy_repository import SqlAlchemyIncidentRepository
from uptime_platform.maintenance.sqlalchemy_repository import (
    SqlAlchemyMaintenanceWindowRepository,
)
from uptime_platform.monitors.entities import (
    HttpMonitorConfig,
    Monitor,
    MonitorStatus,
    MonitorType,
)
from uptime_platform.monitors.models import MonitorModel
from uptime_platform.monitors.sqlalchemy_repository import SqlAlchemyMonitorRepository
from uptime_platform.notifications.entities import NotificationDestinationType
from uptime_platform.notifications.models import (
    NotificationDeliveryModel,
    NotificationDestinationModel,
)
from uptime_platform.notifications.worker import NotificationWorker
from uptime_platform.organizations.models import OrganizationModel
from uptime_platform.outbox.entities import OutboxEventType
from uptime_platform.outbox.models import OutboxEventModel
from uptime_platform.outbox.sqlalchemy_repository import SqlAlchemyOutboxRepository
from uptime_platform.scheduler.scheduler import Scheduler

pytestmark = pytest.mark.anyio
FAILURE = CheckResult(False, 10, 503, "Unexpected HTTP status code: 503")
SUCCESS = CheckResult(True, 10, 200, None)


@pytest.fixture
async def target(session_factory):
    now = datetime.now(UTC)
    monitor = Monitor(
        uuid4(),
        uuid4(),
        "Original API",
        MonitorType.HTTP,
        HttpMonitorConfig(
            "https://user:private-password@original.example.com/health?key=private-key"
        ),
        60,
        5,
        MonitorStatus.UP,
        now,
        now,
        failure_threshold=1,
        recovery_threshold=1,
    )
    async with session_factory() as session, session.begin():
        session.add(
            OrganizationModel(
                id=monitor.organization_id, name="Notification test", created_at=now
            )
        )
        await session.flush()
        await SqlAlchemyMonitorRepository(session).create(monitor)
    try:
        yield monitor
    finally:
        async with session_factory() as session, session.begin():
            await session.execute(
                delete(OrganizationModel).where(
                    OrganizationModel.id == monitor.organization_id
                )
            )


def service(session, monitor, factory=None):
    return CheckService(
        SqlAlchemyMonitorRepository(session),
        SqlAlchemyCheckRepository(session),
        SqlAlchemyIncidentRepository(session),
        SqlAlchemyOutboxRepository(session),
        factory or CheckerFactory(),
        SqlAlchemyMaintenanceWindowRepository(session),
        monitor.organization_id,
    )


async def test_snapshot_survives_rename_deletion_and_worker_retry(
    session_factory, target
):
    destination_id = uuid4()
    async with session_factory() as session, session.begin():
        await service(session, target).record(target.id, FAILURE)
        session.add(
            NotificationDestinationModel(
                id=destination_id,
                organization_id=target.organization_id,
                name="Webhook",
                destination_type=NotificationDestinationType.WEBHOOK,
                enabled=True,
                config={
                    "url": "https://webhook.example.com",
                    "secret": "signing-secret",
                },
                created_at=datetime.now(UTC),
            )
        )
    async with session_factory() as session, session.begin():
        repository = SqlAlchemyMonitorRepository(session)
        current = await repository.get_by_id(target.id, target.organization_id)
        await repository.update(
            replace(
                current,
                name="Renamed API",
                config=HttpMonitorConfig("https://new.example.com"),
            )
        )
        await service(session, target).record(target.id, SUCCESS)
    async with session_factory() as session, session.begin():
        incidents = (
            await session.scalars(
                select(IncidentModel).where(IncidentModel.monitor_id == target.id)
            )
        ).all()
        assert len(incidents) == 1
        started, resolved = incidents[0].started_at, incidents[0].resolved_at
        events = (
            await session.scalars(
                select(OutboxEventModel).where(
                    OutboxEventModel.organization_id == target.organization_id
                )
            )
        ).all()
        snapshots = {event.event_type: dict(event.payload) for event in events}
        assert (
            snapshots[OutboxEventType.INCIDENT_OPENED]["monitor_name"] == "Original API"
        )
        assert (
            snapshots[OutboxEventType.INCIDENT_OPENED]["target"]
            == "https://original.example.com/health"
        )
        recovery = snapshots[OutboxEventType.INCIDENT_RESOLVED]
        assert recovery["monitor_name"] == "Renamed API"
        assert datetime.fromisoformat(recovery["started_at"]) == started
        assert datetime.fromisoformat(recovery["resolved_at"]) == resolved
        await SqlAlchemyMonitorRepository(session).delete(
            target.id, target.organization_id
        )
    requests = {}

    def handler(request):
        payload = json.loads(request.content)
        items = requests.setdefault(payload["id"], [])
        items.append(request.content)
        return httpx2.Response(503 if len(items) == 1 else 200)

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        worker = NotificationWorker(
            session_factory, client, public_app_url="https://uptime.example.com"
        )
        await worker.run_once()
        async with session_factory() as session, session.begin():
            deliveries = (
                await session.scalars(
                    select(NotificationDeliveryModel).where(
                        NotificationDeliveryModel.destination_id == destination_id
                    )
                )
            ).all()
            assert len(deliveries) == 2
            assert all(
                item.attempts == 1 and item.processed_at is None for item in deliveries
            )
            for delivery in deliveries:
                delivery.next_attempt_at = datetime.now(UTC)
        await worker.run_once()
    assert len(requests) == 2
    for bodies in requests.values():
        assert len(bodies) == 2 and bodies[0] == bodies[1]
        assert b"private-password" not in bodies[0] and b"private-key" not in bodies[0]
        payload = json.loads(bodies[0])["payload"]
        assert (
            payload["monitor_url"] == f"https://uptime.example.com/monitors/{target.id}"
        )
    async with session_factory() as session:
        assert await session.get(MonitorModel, target.id) is None
        deliveries = (
            await session.scalars(
                select(NotificationDeliveryModel).where(
                    NotificationDeliveryModel.destination_id == destination_id
                )
            )
        ).all()
        assert all(
            item.attempts == 2
            and item.processed_at is not None
            and item.lease_token is None
            for item in deliveries
        )


async def test_incident_snapshot_rolls_back_with_check_and_monitor(
    session_factory, target
):
    async with session_factory() as session:
        await service(session, target).record(target.id, FAILURE)
        assert (
            await session.scalar(
                select(OutboxEventModel).where(
                    OutboxEventModel.organization_id == target.organization_id
                )
            )
            is not None
        )
        await session.rollback()
    async with session_factory() as session:
        assert (
            await session.scalar(
                select(OutboxEventModel).where(
                    OutboxEventModel.organization_id == target.organization_id
                )
            )
            is None
        )
        assert (
            await session.scalar(
                select(IncidentModel).where(IncidentModel.monitor_id == target.id)
            )
            is None
        )
        assert (
            await session.scalar(
                select(CheckModel).where(CheckModel.monitor_id == target.id)
            )
            is None
        )
        assert (await session.get(MonitorModel, target.id)).status is MonitorStatus.UP


@pytest.mark.parametrize("scheduled", [False, True])
async def test_inflight_check_reports_checked_target_without_overwriting_edit(
    session_factory, target, scheduled
):
    started, release = asyncio.Event(), asyncio.Event()

    class BlockingFactory:
        def create(self, monitor):
            assert monitor.config.url == target.config.url
            return self

        async def check(self, timeout_seconds):
            started.set()
            await release.wait()
            return FAILURE

    factory = BlockingFactory()

    async def run():
        if scheduled:
            await Scheduler(session_factory, checker_factory=factory).run_once()
        else:
            async with session_factory() as session, session.begin():
                await service(session, target, factory).run(target.id)

    async with asyncio.timeout(5), asyncio.TaskGroup() as group:
        group.create_task(run())
        await started.wait()
        async with session_factory() as session, session.begin():
            await session.execute(
                update(MonitorModel)
                .where(MonitorModel.id == target.id)
                .values(
                    name="Changed during probe",
                    config={"url": "https://edited.example.com"},
                )
            )
        release.set()
    async with session_factory() as session:
        saved = await session.scalar(
            select(OutboxEventModel).where(
                OutboxEventModel.organization_id == target.organization_id
            )
        )
        assert saved.payload["target"] == "https://original.example.com/health"
        assert saved.payload["monitor_name"] == "Original API"
        current = await session.get(MonitorModel, target.id)
        assert current.name == "Changed during probe"
        assert current.config["url"] == "https://edited.example.com"
        assert current.status is MonitorStatus.DOWN
