import asyncio
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, update

from uptime_platform.core.metrics import Metrics
from uptime_platform.notifications import worker as worker_module
from uptime_platform.notifications.entities import (
    NotificationDelivery,
    NotificationDestinationType,
)
from uptime_platform.notifications.models import (
    NotificationDeliveryModel,
    NotificationDestinationModel,
)
from uptime_platform.notifications.sqlalchemy_repository import (
    SqlAlchemyNotificationDeliveryRepository,
)
from uptime_platform.notifications.worker import NotificationWorker
from uptime_platform.organizations.models import OrganizationModel
from uptime_platform.outbox.entities import OutboxEventType
from uptime_platform.outbox.models import OutboxEventModel

pytestmark = pytest.mark.anyio


@pytest.fixture
async def deliveries(session_factory):
    organization_id = uuid4()
    destination_id = uuid4()
    now = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        session.add(
            OrganizationModel(id=organization_id, name="Worker test", created_at=now)
        )
        await session.flush()
        session.add(
            NotificationDestinationModel(
                id=destination_id,
                organization_id=organization_id,
                name="Webhook",
                destination_type=NotificationDestinationType.WEBHOOK,
                enabled=True,
                config={"url": "https://example.com", "secret": "test"},
                created_at=now,
            )
        )

    async def create(count=1):
        result = []
        async with session_factory() as session, session.begin():
            for _ in range(count):
                event_id = uuid4()
                session.add(
                    OutboxEventModel(
                        id=event_id,
                        organization_id=organization_id,
                        event_type=OutboxEventType.INCIDENT_OPENED,
                        payload={},
                        created_at=now,
                        processed_at=now,
                    )
                )
                await session.flush()
                delivery = NotificationDelivery(
                    id=uuid4(),
                    event_id=event_id,
                    destination_id=destination_id,
                    created_at=now,
                    processed_at=None,
                    attempts=0,
                    last_error=None,
                    next_attempt_at=now,
                    locked_until=None,
                )
                result.append(
                    await SqlAlchemyNotificationDeliveryRepository(session).create(
                        delivery
                    )
                )
        return result

    try:
        yield create
    finally:
        async with session_factory() as session, session.begin():
            await session.execute(
                delete(OrganizationModel).where(OrganizationModel.id == organization_id)
            )


async def claim(session_factory, **kwargs):
    async with session_factory() as session, session.begin():
        return await SqlAlchemyNotificationDeliveryRepository(session).claim_pending(
            limit=kwargs.pop("limit", 1),
            max_attempts=5,
            lease_seconds=kwargs.pop("lease_seconds", 60),
            **kwargs,
        )


async def expire(session_factory, delivery_id):
    async with session_factory() as session, session.begin():
        await session.execute(
            update(NotificationDeliveryModel)
            .where(NotificationDeliveryModel.id == delivery_id)
            .values(locked_until=func.clock_timestamp() - timedelta(seconds=1))
        )


class Sends:
    def __init__(self, expected=1, blocked=False):
        self.calls = Counter()
        self.active = 0
        self.started = asyncio.Event()
        self.gate = asyncio.Event()
        self.expected = expected
        if not blocked:
            self.gate.set()

    async def send(self, event):
        self.calls[event.id] += 1
        self.active += 1
        if self.active >= self.expected:
            self.started.set()
        try:
            await self.gate.wait()
        finally:
            self.active -= 1


def worker(session_factory, sends, monkeypatch, **kwargs):
    monkeypatch.setattr(worker_module, "create_notification_channel", lambda **_: sends)
    return NotificationWorker(
        session_factory, MagicMock(), metrics=Metrics("worker"), **kwargs
    )


async def test_claim_skips_locked_rows_and_commits_distinct_tokens(
    session_factory, deliveries
):
    items = await deliveries(2)
    async with session_factory() as first, first.begin():
        a = await SqlAlchemyNotificationDeliveryRepository(first).claim_pending(
            limit=1, max_attempts=5, lease_seconds=60
        )
        async with asyncio.timeout(2):
            b = await claim(session_factory)
        assert {a[0].id, b[0].id} == {d.id for d in items}
        assert a[0].lease_token != b[0].lease_token
    assert await claim(session_factory, limit=10) == []


async def test_two_workers_only_claim_capacity_and_send_each_delivery_once(
    session_factory, deliveries, monkeypatch
):
    items = await deliveries(6)
    sends = Sends(expected=2, blocked=True)
    workers = [
        worker(session_factory, sends, monkeypatch, batch_size=3, concurrency=1)
        for _ in range(2)
    ]
    async with asyncio.timeout(8):
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(w.run_once()) for w in workers]
            await sends.started.wait()
            async with session_factory() as session:
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(NotificationDeliveryModel)
                        .where(NotificationDeliveryModel.lease_token.is_not(None))
                    )
                    == 2
                )
            sends.gate.set()
    assert sum(t.result()[1] for t in tasks) == 6
    assert sends.calls == Counter({d.event_id: 1 for d in items})
    async with session_factory() as session:
        rows = (
            await session.scalars(
                select(NotificationDeliveryModel).where(
                    NotificationDeliveryModel.id.in_([d.id for d in items])
                )
            )
        ).all()
        assert all(r.processed_at is not None and r.attempts == 1 for r in rows)
        assert all(r.lease_token is None and r.locked_until is None for r in rows)
    assert all(
        w._metrics.registry.get_sample_value(
            "uptime_notification_worker_last_success_timestamp_seconds"
        )
        > 0
        for w in workers
    )


async def test_abandoned_lease_is_recovered_by_worker_after_expiry(
    session_factory, deliveries, monkeypatch
):
    item = (await deliveries())[0]
    old = (await claim(session_factory, lease_seconds=0.2))[0]
    sends = Sends()
    replacement = worker(session_factory, sends, monkeypatch)
    assert await claim(session_factory) == []
    await asyncio.sleep(0.22)
    assert await replacement.run_once() == (0, 1)
    assert sends.calls[item.event_id] == 1
    async with session_factory() as session, session.begin():
        assert not await SqlAlchemyNotificationDeliveryRepository(session).release_lock(
            item.id, old.lease_token
        )


async def test_expired_owner_cannot_update_or_release_new_claim(
    session_factory, deliveries
):
    item = (await deliveries())[0]
    old = (await claim(session_factory))[0]
    await expire(session_factory, item.id)
    async with session_factory() as session, session.begin():
        repository = SqlAlchemyNotificationDeliveryRepository(session)
        assert (
            await repository.update(
                replace(old, attempts=1, processed_at=datetime.now(UTC)),
                lease_token=old.lease_token,
            )
            is None
        )
    new = (await claim(session_factory))[0]
    assert new.lease_token != old.lease_token
    async with session_factory() as session, session.begin():
        repository = SqlAlchemyNotificationDeliveryRepository(session)
        assert (
            await repository.update(
                replace(old, attempts=4), lease_token=old.lease_token
            )
            is None
        )
        assert not await repository.release_lock(item.id, old.lease_token)
        row = await repository.get_by_id(item.id)
        assert row.lease_token == new.lease_token and row.attempts == 0
        assert (
            await repository.update(
                replace(new, attempts=1, processed_at=datetime.now(UTC)),
                lease_token=new.lease_token,
            )
            is not None
        )


async def test_expiry_is_checked_after_waiting_for_row_lock(
    session_factory, deliveries
):
    await deliveries()
    owned = (await claim(session_factory))[0]
    async with session_factory() as blocker:
        async with blocker.begin():
            await blocker.execute(
                update(NotificationDeliveryModel)
                .where(NotificationDeliveryModel.id == owned.id)
                .values(locked_until=func.clock_timestamp() + timedelta(seconds=0.15))
            )

            async def finish():
                async with session_factory() as session, session.begin():
                    return await SqlAlchemyNotificationDeliveryRepository(
                        session
                    ).update(replace(owned, attempts=1), lease_token=owned.lease_token)

            task = asyncio.create_task(finish())
            await asyncio.sleep(0.2)
            assert not task.done()
        async with asyncio.timeout(2):
            assert await task is None


async def test_late_send_result_cannot_overwrite_replacement_worker(
    session_factory, deliveries, monkeypatch
):
    item = (await deliveries())[0]
    old_sends = Sends(blocked=True)
    old_worker = worker(session_factory, old_sends, monkeypatch, batch_size=1)
    async with asyncio.timeout(8):
        async with asyncio.TaskGroup() as group:
            task = group.create_task(old_worker.run_once())
            await old_sends.started.wait()
            await expire(session_factory, item.id)
            replacement_sends = Sends()
            replacement = worker(
                session_factory, replacement_sends, monkeypatch, batch_size=1
            )
            assert await replacement.run_once() == (0, 1)
            old_sends.gate.set()
        assert task.result() == (0, 1)
    async with session_factory() as session:
        row = await session.get(NotificationDeliveryModel, item.id)
        assert row.processed_at is not None and row.attempts == 1
        assert row.lease_token is None
    assert (
        old_worker._metrics.registry.get_sample_value(
            "uptime_notification_worker_last_success_timestamp_seconds"
        )
        == 0
    )


async def test_expired_claim_is_not_sent(session_factory, deliveries, monkeypatch):
    item = (await deliveries())[0]
    owned = (await claim(session_factory))[0]
    await expire(session_factory, item.id)
    sends = Sends()
    instance = worker(session_factory, sends, monkeypatch)
    assert await instance._process_delivery(owned) is False
    assert not sends.calls


async def test_total_timeout_persists_retry_and_clears_lease(
    session_factory, deliveries, monkeypatch
):
    item = (await deliveries())[0]
    sends = Sends(blocked=True)
    instance = worker(
        session_factory, sends, monkeypatch, notification_timeout_seconds=0.02
    )
    async with asyncio.timeout(3):
        assert await instance.run_once() == (0, 1)
    assert sends.active == 0
    async with session_factory() as session:
        row = await session.get(NotificationDeliveryModel, item.id)
        assert row.attempts == 1 and row.processed_at is None
        assert "total timeout" in row.last_error
        assert row.next_attempt_at > datetime.now(UTC)
        assert row.lease_token is None and row.locked_until is None
    assert await instance.run_once() == (0, 0)


async def test_cancellation_drains_tasks_and_releases_for_next_worker(
    session_factory, deliveries, monkeypatch
):
    item = (await deliveries())[0]
    sends = Sends(blocked=True)
    instance = worker(session_factory, sends, monkeypatch)
    async with asyncio.timeout(5):
        task = asyncio.create_task(instance.run_once())
        await sends.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert sends.active == 0
    async with session_factory() as session:
        row = await session.get(NotificationDeliveryModel, item.id)
        assert row.lease_token is None and row.processed_at is None
    replacement = worker(session_factory, Sends(), monkeypatch)
    assert await replacement.run_once() == (0, 1)


async def test_persistence_error_releases_claim_without_repeating_same_cycle(
    session_factory, deliveries, monkeypatch
):
    item = (await deliveries())[0]
    sends = Sends()
    instance = worker(session_factory, sends, monkeypatch)
    original_update = SqlAlchemyNotificationDeliveryRepository.update

    async def fail_after_flush(repository, delivery, *, lease_token):
        await original_update(repository, delivery, lease_token=lease_token)
        raise RuntimeError("database failure after flush")

    monkeypatch.setattr(
        SqlAlchemyNotificationDeliveryRepository, "update", fail_after_flush
    )
    assert await instance.run_once() == (0, 1)
    assert sends.calls[item.event_id] == 1
    async with session_factory() as session:
        row = await session.get(NotificationDeliveryModel, item.id)
        assert row.processed_at is None and row.attempts == 0
        assert row.lease_token is None and row.locked_until is None
    assert (
        instance._metrics.registry.get_sample_value(
            "uptime_notification_worker_last_success_timestamp_seconds"
        )
        == 0
    )
