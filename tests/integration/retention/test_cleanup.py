import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from uptime_platform.checks.models import CheckModel
from uptime_platform.core.config import Settings
from uptime_platform.incidents.entities import IncidentStatus
from uptime_platform.incidents.models import IncidentModel
from uptime_platform.monitors.entities import MonitorType
from uptime_platform.monitors.models import MonitorModel
from uptime_platform.notifications.entities import NotificationDestinationType
from uptime_platform.notifications.models import (
    NotificationDeliveryModel,
    NotificationDestinationModel,
)
from uptime_platform.organizations.models import OrganizationModel
from uptime_platform.outbox.entities import OutboxEventType
from uptime_platform.outbox.models import OutboxEventModel
from uptime_platform.retention.repository import RetentionRepository
from uptime_platform.retention.service import RetentionService

pytestmark = pytest.mark.anyio
NOW = datetime(2000, 6, 1, tzinfo=UTC)


@pytest.fixture
async def records(session_factory):
    organization_id, monitor_id, destination_id = uuid4(), uuid4(), uuid4()
    second_destination_id = uuid4()
    async with session_factory() as session, session.begin():
        session.add(
            OrganizationModel(
                id=organization_id,
                name="Retention test",
                created_at=NOW,
            )
        )
        await session.flush()
        session.add_all(
            [
                MonitorModel(
                    id=monitor_id,
                    organization_id=organization_id,
                    name="Monitor",
                    monitor_type=MonitorType.HTTP,
                    config={"url": "https://example.com"},
                    next_check_at=NOW,
                ),
                NotificationDestinationModel(
                    id=destination_id,
                    organization_id=organization_id,
                    name="Webhook",
                    destination_type=NotificationDestinationType.WEBHOOK,
                    enabled=True,
                    config={"url": "https://example.com"},
                    created_at=NOW,
                ),
                NotificationDestinationModel(
                    id=second_destination_id,
                    organization_id=organization_id,
                    name="Second webhook",
                    destination_type=NotificationDestinationType.WEBHOOK,
                    enabled=True,
                    config={"url": "https://example.org"},
                    created_at=NOW,
                ),
            ]
        )

    async def create(kind, at, **kwargs):
        async with session_factory() as session, session.begin():
            if kind == "check":
                row = CheckModel(
                    monitor_id=monitor_id,
                    success=True,
                    response_time_ms=1,
                    checked_at=at,
                    **kwargs,
                )
            elif kind == "incident":
                row = IncidentModel(
                    monitor_id=monitor_id,
                    status=kwargs.pop("status", IncidentStatus.RESOLVED),
                    started_at=NOW - timedelta(days=365),
                    resolved_at=at,
                    **kwargs,
                )
            elif kind == "event":
                row = OutboxEventModel(
                    id=uuid4(),
                    organization_id=organization_id,
                    event_type=OutboxEventType.INCIDENT_RESOLVED,
                    payload={},
                    created_at=NOW - timedelta(days=365),
                    processed_at=at,
                    **kwargs,
                )
            else:
                row = NotificationDeliveryModel(
                    id=uuid4(),
                    destination_id=(
                        second_destination_id
                        if kwargs.pop("second", False)
                        else destination_id
                    ),
                    created_at=NOW - timedelta(days=365),
                    processed_at=at,
                    next_attempt_at=NOW,
                    **kwargs,
                )
            session.add(row)
            await session.flush()
            return row.id

    try:
        yield create
    finally:
        async with session_factory() as session, session.begin():
            await session.execute(
                delete(OrganizationModel).where(OrganizationModel.id == organization_id)
            )


def settings(**kwargs):
    return Settings(_env_file=None, database_url="unused", **kwargs)


async def cleanup(session_factory, **kwargs):
    async with session_factory() as session, session.begin():
        return await RetentionRepository(session).cleanup(
            settings=settings(**kwargs),
            now=NOW,
        )


async def exists(session_factory, model, row_id):
    async with session_factory() as session:
        return await session.get(model, row_id) is not None


@pytest.mark.parametrize(
    ("kind", "model", "option"),
    [
        ("check", CheckModel, "retention_checks_days"),
        ("incident", IncidentModel, "retention_incidents_days"),
        ("event", OutboxEventModel, "retention_notifications_days"),
    ],
)
async def test_strict_boundary_and_custom_period(
    session_factory,
    records,
    kind,
    model,
    option,
):
    cutoff = NOW - timedelta(days=7)
    old = await records(kind, cutoff - timedelta(microseconds=1))
    boundary = await records(kind, cutoff)
    recent = await records(kind, cutoff + timedelta(microseconds=1))
    counts = await cleanup(session_factory, **{option: 7})
    assert sum(counts.values()) == 1
    assert not await exists(session_factory, model, old)
    assert await exists(session_factory, model, boundary)
    assert await exists(session_factory, model, recent)
    assert not any((await cleanup(session_factory, **{option: 7})).values())


async def test_delivery_age_uses_completion_and_preserves_parent_until_empty(
    session_factory,
    records,
):
    cutoff = NOW - timedelta(days=7)
    event = await records("event", NOW - timedelta(days=100))
    old = await records("delivery", cutoff - timedelta(microseconds=1), event_id=event)
    boundary_event = await records("event", NOW - timedelta(days=100))
    boundary = await records("delivery", cutoff, event_id=boundary_event)
    recent_event = await records("event", NOW - timedelta(days=100))
    recent = await records(
        "delivery", cutoff + timedelta(microseconds=1), event_id=recent_event
    )
    counts = await cleanup(session_factory, retention_notifications_days=7)
    assert counts["deliveries"] == 1 and counts["events"] == 1
    assert not await exists(session_factory, NotificationDeliveryModel, old)
    assert not await exists(session_factory, OutboxEventModel, event)
    for delivery_id, event_id in [(boundary, boundary_event), (recent, recent_event)]:
        assert await exists(session_factory, NotificationDeliveryModel, delivery_id)
        assert await exists(session_factory, OutboxEventModel, event_id)
    assert not any(
        (await cleanup(session_factory, retention_notifications_days=7)).values()
    )


async def test_open_incidents_and_unprocessed_events_survive(session_factory, records):
    incident = await records("incident", None, status=IncidentStatus.OPEN)
    event = await records("event", None)
    delivery = await records("delivery", NOW - timedelta(days=100), event_id=event)
    unresolved = await records("incident", None)
    assert not any((await cleanup(session_factory)).values())
    for model, row_id in [
        (IncidentModel, incident),
        (IncidentModel, unresolved),
        (OutboxEventModel, event),
        (NotificationDeliveryModel, delivery),
    ]:
        assert await exists(session_factory, model, row_id)


@pytest.mark.parametrize(
    "state", ["pending", "exhausted", "leased", "completed_leased"]
)
async def test_event_cascade_cannot_remove_protected_deliveries(
    session_factory,
    records,
    state,
):
    old = NOW - timedelta(days=100)
    event = await records("event", old)
    completed_at = old if state == "completed_leased" else None
    lease = state in {"leased", "completed_leased"}
    delivery = await records(
        "delivery",
        completed_at,
        event_id=event,
        attempts=5 if state == "exhausted" else 0,
        lease_token=uuid4() if lease else None,
        locked_until=NOW + timedelta(seconds=60) if lease else None,
    )
    assert not any((await cleanup(session_factory)).values())
    assert await exists(session_factory, OutboxEventModel, event)
    assert await exists(session_factory, NotificationDeliveryModel, delivery)


async def test_batches_are_bounded_including_cascades_and_repeated_runs(
    session_factory,
    records,
):
    old = NOW - timedelta(days=100)
    for _ in range(3):
        await records("check", old)
        await records("incident", old)
        event = await records("event", old)
        await records("delivery", old, event_id=event)
        await records("delivery", old, event_id=event, second=True)
    totals = {"checks": 0, "incidents": 0, "deliveries": 0, "events": 0}
    for _ in range(7):
        counts = await cleanup(session_factory, retention_batch_size=1)
        for kind, count in counts.items():
            assert 0 <= count <= 1
            totals[kind] += count
    assert totals == {"checks": 3, "incidents": 3, "deliveries": 6, "events": 3}
    assert not any((await cleanup(session_factory)).values())


async def test_two_cleaners_skip_locked_records(session_factory, records):
    old = NOW - timedelta(days=100)
    ids = [await records("check", old) for _ in range(4)]
    async with session_factory() as first, first.begin():
        first_counts = await RetentionRepository(first).cleanup(
            settings=settings(retention_batch_size=2),
            now=NOW,
        )
        async with asyncio.timeout(2):
            second_counts = await cleanup(session_factory, retention_batch_size=2)
        assert first_counts["checks"] == second_counts["checks"] == 2
    for row_id in ids:
        assert not await exists(session_factory, CheckModel, row_id)


@pytest.mark.parametrize("failure", ["error", "cancel", "timeout"])
async def test_failed_or_cancelled_pass_rolls_back_and_can_retry(
    session_factory,
    records,
    monkeypatch,
    failure,
):
    row_id = await records("check", NOW - timedelta(days=100))
    original = RetentionRepository._delete_batch
    started = asyncio.Event()

    async def interrupt(repository, *args, **kwargs):
        count = await original(repository, *args, **kwargs)
        if count:
            started.set()
            if failure != "error":
                await asyncio.Event().wait()
            raise RuntimeError("test failure after delete")
        return count

    monkeypatch.setattr(RetentionRepository, "_delete_batch", interrupt)
    timeout = asyncio.timeout
    monkeypatch.setattr(
        asyncio, "timeout", lambda delay: timeout(0.1 if delay == 30 else delay)
    )
    service = RetentionService(session_factory, settings())
    async with asyncio.timeout(3):
        task = asyncio.create_task(service.run_once())
        await started.wait()
        if failure == "cancel":
            task.cancel()
        exception = {
            "error": RuntimeError,
            "cancel": asyncio.CancelledError,
            "timeout": TimeoutError,
        }[failure]
        with pytest.raises(exception):
            await task
    assert await exists(session_factory, CheckModel, row_id)
    monkeypatch.setattr(RetentionRepository, "_delete_batch", original)
    assert (await cleanup(session_factory))["checks"] == 1


async def test_cleanup_skips_rows_locked_by_another_transaction(
    session_factory, records
):
    row_id = await records("check", NOW - timedelta(days=100))
    async with session_factory() as session, session.begin():
        await session.execute(
            select(CheckModel).where(CheckModel.id == row_id).with_for_update()
        )
        async with asyncio.timeout(2):
            assert (await cleanup(session_factory))["checks"] == 0
    assert (await cleanup(session_factory))["checks"] == 1
