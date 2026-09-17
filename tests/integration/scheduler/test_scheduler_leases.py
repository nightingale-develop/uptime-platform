import asyncio
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, update

from uptime_platform.checks.entities import CheckResult
from uptime_platform.checks.models import CheckModel
from uptime_platform.checks.service import CheckService
from uptime_platform.checks.sqlalchemy_repository import SqlAlchemyCheckRepository
from uptime_platform.incidents.models import IncidentModel
from uptime_platform.incidents.sqlalchemy_repository import SqlAlchemyIncidentRepository
from uptime_platform.maintenance.entities import MaintenanceWindow
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
from uptime_platform.organizations.models import OrganizationModel
from uptime_platform.outbox.models import OutboxEventModel
from uptime_platform.outbox.sqlalchemy_repository import SqlAlchemyOutboxRepository
from uptime_platform.scheduler.scheduler import Scheduler

pytestmark = pytest.mark.anyio

SUCCESS = CheckResult(True, 1, 200, None)
FAILURE = CheckResult(False, 1, 503, "Unavailable")


class Probes:
    def __init__(self, result=SUCCESS, blocked=False, expected_started=1):
        self.result = result
        self.gate = asyncio.Event()
        if not blocked:
            self.gate.set()
        self.started = asyncio.Event()
        self.expected_started = expected_started
        self.calls = Counter()
        self.active = Counter()
        self.peak = Counter()

    def create(self, monitor):
        parent = self

        class Checker:
            async def check(self, timeout_seconds):
                parent.calls[monitor.id] += 1
                parent.active[monitor.id] += 1
                parent.peak[monitor.id] = max(
                    parent.peak[monitor.id], parent.active[monitor.id]
                )
                if sum(parent.calls.values()) >= parent.expected_started:
                    parent.started.set()
                try:
                    await parent.gate.wait()
                    return parent.result
                finally:
                    parent.active[monitor.id] -= 1

        return Checker()


@pytest.fixture
async def make_monitor(session_factory, db_session):
    organization_id = uuid4()
    async with session_factory() as session, session.begin():
        session.add(
            OrganizationModel(
                id=organization_id,
                name="Scheduler integration test",
                created_at=datetime.now(UTC),
            )
        )

    async def create(**changes):
        now = datetime.now(UTC)
        monitor = replace(
            Monitor(
                id=uuid4(),
                organization_id=organization_id,
                name="Lease test",
                monitor_type=MonitorType.HTTP,
                config=HttpMonitorConfig(url="https://example.com"),
                interval_seconds=60,
                timeout_seconds=10,
                status=MonitorStatus.PENDING,
                created_at=now,
                next_check_at=now - timedelta(seconds=1),
                failure_threshold=1,
            ),
            **changes,
        )
        async with session_factory() as session, session.begin():
            await SqlAlchemyMonitorRepository(session).create(monitor)
        return monitor

    try:
        yield create
    finally:
        async with session_factory() as session, session.begin():
            await session.execute(
                delete(OrganizationModel).where(OrganizationModel.id == organization_id)
            )


async def claim(session_factory, limit=1):
    async with session_factory() as session, session.begin():
        return await SqlAlchemyMonitorRepository(session).claim_due(
            limit=limit, lease_grace_seconds=30
        )


async def expire(session_factory, monitor_id):
    async with session_factory() as session, session.begin():
        await session.execute(
            update(MonitorModel)
            .where(MonitorModel.id == monitor_id)
            .values(check_lease_until=func.clock_timestamp() - timedelta(seconds=1))
        )


def service(session, monitor, factory=None):
    return CheckService(
        monitor_repository=SqlAlchemyMonitorRepository(session),
        check_repository=SqlAlchemyCheckRepository(session),
        incident_repository=SqlAlchemyIncidentRepository(session),
        outbox_repository=SqlAlchemyOutboxRepository(session),
        checker_factory=factory or Probes(),
        maintenance_repository=SqlAlchemyMaintenanceWindowRepository(session),
        organization_id=monitor.organization_id,
    )


async def test_skip_locked_does_not_wait_for_an_uncommitted_claim(
    session_factory, make_monitor
):
    monitors = [await make_monitor(), await make_monitor()]
    async with session_factory() as first, first.begin():
        a = await SqlAlchemyMonitorRepository(first).claim_due(
            limit=1, lease_grace_seconds=30
        )
        async with asyncio.timeout(3):
            b = await claim(session_factory)
        assert {a[0].monitor.id, b[0].monitor.id} == {m.id for m in monitors}
    assert await claim(session_factory, limit=10) == []


async def test_two_schedulers_process_each_monitor_only_once(
    session_factory, make_monitor
):
    from uptime_platform.core.metrics import Metrics

    monitors = [await make_monitor() for _ in range(4)]
    probes = Probes(result=FAILURE, blocked=True, expected_started=2)
    metrics = [Metrics("scheduler") for _ in range(2)]
    schedulers = [
        Scheduler(
            session_factory,
            batch_size=2,
            concurrency=1,
            checker_factory=probes,
            metrics=instance,
        )
        for instance in metrics
    ]
    async with asyncio.timeout(8):
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(s.run_once()) for s in schedulers]
            await probes.started.wait()
            async with session_factory() as session:
                leased = await session.scalar(
                    select(func.count())
                    .select_from(MonitorModel)
                    .where(MonitorModel.check_lease_token.is_not(None))
                )
            assert leased == 2  # No preclaimed semaphore backlog.
            probes.gate.set()
    assert sum(t.result() for t in tasks) == 4
    for instance in metrics:
        assert (
            instance.registry.get_sample_value(
                "uptime_checks_total", {"monitor_type": "http", "outcome": "failure"}
            )
            == 2
        )
        assert (
            instance.registry.get_sample_value(
                "uptime_check_duration_seconds_count", {"monitor_type": "http"}
            )
            == 2
        )
        assert (
            instance.registry.get_sample_value(
                "uptime_scheduler_last_success_timestamp_seconds"
            )
            > 0
        )
    assert probes.calls == Counter({m.id: 1 for m in monitors})
    assert all(peak == 1 for peak in probes.peak.values())
    async with session_factory() as session:
        for model in (CheckModel, IncidentModel, OutboxEventModel):
            assert await session.scalar(select(func.count()).select_from(model)) == 4
        rows = (await session.scalars(select(MonitorModel))).all()
        assert all(row.check_lease_token is None for row in rows)
        assert all(row.status is MonitorStatus.DOWN for row in rows)
        assert all(row.consecutive_failures == 1 for row in rows)


async def test_abandoned_claim_is_recovered_after_expiry(session_factory, make_monitor):
    monitor = await make_monitor()
    abandoned = (await claim(session_factory))[0]
    probes = Probes()
    survivor = Scheduler(session_factory, checker_factory=probes)
    assert await survivor.run_once() == 0
    await expire(session_factory, monitor.id)
    assert await survivor.run_once() == 1
    assert probes.calls[monitor.id] == 1
    async with session_factory() as session, session.begin():
        assert (
            await service(session, monitor).record(
                monitor.id, FAILURE, lease_token=abandoned.token
            )
            is None
        )
        assert not await SqlAlchemyMonitorRepository(session).release_check_lease(
            monitor.id, abandoned.token
        )
    async with session_factory() as session:
        checks = (await session.scalars(select(CheckModel))).all()
        assert len(checks) == 1 and checks[0].success
        assert (
            await session.scalar(select(func.count()).select_from(IncidentModel)) == 0
        )


async def test_expired_and_replaced_owner_cannot_write_or_release(
    session_factory, make_monitor
):
    monitor = await make_monitor()
    old = (await claim(session_factory))[0]
    await expire(session_factory, monitor.id)
    async with session_factory() as session, session.begin():
        assert (
            await service(session, monitor).record(
                monitor.id, FAILURE, lease_token=old.token
            )
            is None
        )  # Expiry alone is sufficient, even before a replacement.
    new = (await claim(session_factory))[0]
    assert new.token != old.token
    async with session_factory() as session, session.begin():
        assert (
            await service(session, monitor).record(
                monitor.id, FAILURE, lease_token=old.token
            )
            is None
        )
        assert not await SqlAlchemyMonitorRepository(session).release_check_lease(
            monitor.id, old.token
        )
    async with session_factory() as session:
        row = await session.get(MonitorModel, monitor.id)
        assert row.check_lease_token == new.token
        assert row.status is MonitorStatus.PENDING
        assert await session.scalar(select(func.count()).select_from(CheckModel)) == 0


async def test_late_scheduler_cannot_overwrite_or_release_new_scheduler_claim(
    session_factory, make_monitor
):
    monitor = await make_monitor()
    slow = Probes(result=FAILURE, blocked=True)
    replacement = Probes(result=SUCCESS, blocked=True)
    first = Scheduler(session_factory, batch_size=1, checker_factory=slow)
    second = Scheduler(session_factory, batch_size=1, checker_factory=replacement)

    async with asyncio.timeout(8):
        async with asyncio.TaskGroup() as group:
            old_task = group.create_task(first.run_once())
            await slow.started.wait()
            await expire(session_factory, monitor.id)
            group.create_task(second.run_once())
            await replacement.started.wait()
            async with session_factory() as session:
                new_token = (
                    await session.get(MonitorModel, monitor.id)
                ).check_lease_token

            slow.gate.set()
            await old_task
            async with session_factory() as session:
                row = await session.get(MonitorModel, monitor.id)
                assert row.check_lease_token == new_token
                assert row.status is MonitorStatus.PENDING
                assert (
                    await session.scalar(select(func.count()).select_from(CheckModel))
                    == 0
                )
            replacement.gate.set()

    async with session_factory() as session:
        checks = (await session.scalars(select(CheckModel))).all()
        assert len(checks) == 1 and checks[0].success
        row = await session.get(MonitorModel, monitor.id)
        assert row.status is MonitorStatus.UP
        assert row.check_lease_token is None


async def test_recording_failure_rolls_back_state_and_releases_lease(
    session_factory, make_monitor, monkeypatch
):
    monitor = await make_monitor()

    async def fail_outbox(self, event):
        raise RuntimeError("Simulated persistence failure")

    monkeypatch.setattr(SqlAlchemyOutboxRepository, "create", fail_outbox)
    scheduler = Scheduler(session_factory, checker_factory=Probes(FAILURE))
    assert await scheduler.run_once() == 1
    async with session_factory() as session:
        row = await session.get(MonitorModel, monitor.id)
        assert row.check_lease_token is None
        assert row.status is MonitorStatus.PENDING
        assert row.consecutive_failures == 0
        for model in (CheckModel, IncidentModel, OutboxEventModel):
            assert await session.scalar(select(func.count()).select_from(model)) == 0


async def test_successful_record_and_lease_release_roll_back_together(
    session_factory, make_monitor
):
    monitor = await make_monitor()
    owner = (await claim(session_factory))[0]
    async with session_factory() as session:
        await service(session, monitor).record(
            monitor.id, FAILURE, lease_token=owner.token
        )
        await session.rollback()
    async with session_factory() as session:
        row = await session.get(MonitorModel, monitor.id)
        assert row.check_lease_token == owner.token
        assert row.status is MonitorStatus.PENDING
        assert row.consecutive_failures == 0
        for model in (CheckModel, IncidentModel, OutboxEventModel):
            assert await session.scalar(select(func.count()).select_from(model)) == 0
    async with session_factory() as session, session.begin():
        assert (
            await service(session, monitor).record(
                monitor.id, FAILURE, lease_token=owner.token
            )
            is not None
        )
    async with session_factory() as session:
        row = await session.get(MonitorModel, monitor.id)
        assert row.check_lease_token is None and row.check_lease_until is None
        assert row.status is MonitorStatus.DOWN


async def test_cancellation_releases_claim_and_allows_another_scheduler(
    session_factory, make_monitor
):
    monitor = await make_monitor()
    blocked = Probes(blocked=True)
    scheduler = Scheduler(session_factory, checker_factory=blocked)
    async with asyncio.timeout(8):
        async with asyncio.TaskGroup() as group:
            task = group.create_task(scheduler.run_once())
            await blocked.started.wait()
            task.cancel()
        assert task.cancelled()
    assert blocked.active[monitor.id] == 0
    async with session_factory() as session:
        row = await session.get(MonitorModel, monitor.id)
        assert row.check_lease_token is None
        assert await session.scalar(select(func.count()).select_from(CheckModel)) == 0
    assert await Scheduler(session_factory, checker_factory=Probes()).run_once() == 1


async def test_checker_exception_releases_without_reclaiming_in_same_batch(
    session_factory, make_monitor
):
    monitor = await make_monitor()

    class BrokenFactory:
        calls = 0

        def create(self, monitor):
            self.calls += 1
            raise RuntimeError("Broken checker")

    factory = BrokenFactory()
    assert await Scheduler(session_factory, checker_factory=factory).run_once() == 1
    assert factory.calls == 1
    async with session_factory() as session:
        row = await session.get(MonitorModel, monitor.id)
        assert row.check_lease_token is None
        assert row.status is MonitorStatus.PENDING
    assert await Scheduler(session_factory, checker_factory=Probes()).run_once() == 1


async def test_claim_skips_future_and_paused_monitors_and_rollback_undoes_claim(
    session_factory, make_monitor
):
    due = await make_monitor()
    await make_monitor(status=MonitorStatus.PAUSED)
    await make_monitor(next_check_at=datetime.now(UTC) + timedelta(hours=1))
    async with session_factory() as session:
        owners = await SqlAlchemyMonitorRepository(session).claim_due(
            limit=10, lease_grace_seconds=30
        )
        assert [c.monitor.id for c in owners] == [due.id]
        await session.rollback()
    assert [c.monitor.id for c in await claim(session_factory, 10)] == [due.id]


async def test_regular_update_does_not_clear_lease_and_manual_check_still_works(
    session_factory, make_monitor
):
    monitor = await make_monitor()
    owner = (await claim(session_factory))[0]
    async with session_factory() as session, session.begin():
        await SqlAlchemyMonitorRepository(session).update(
            replace(monitor, name="Renamed")
        )
        assert await service(session, monitor).run(monitor.id) is not None
    async with session_factory() as session:
        row = await session.get(MonitorModel, monitor.id)
        assert row.check_lease_token == owner.token
        assert row.status is MonitorStatus.UP


async def test_maintenance_records_check_and_clears_lease_without_incident(
    session_factory, make_monitor
):
    monitor = await make_monitor()
    now = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        await SqlAlchemyMaintenanceWindowRepository(session).create(
            MaintenanceWindow(
                id=uuid4(),
                monitor_id=monitor.id,
                starts_at=now - timedelta(minutes=1),
                ends_at=now + timedelta(minutes=1),
                reason="Test maintenance",
                created_at=now,
            )
        )
    assert (
        await Scheduler(session_factory, checker_factory=Probes(FAILURE)).run_once()
        == 1
    )
    async with session_factory() as session:
        row = await session.get(MonitorModel, monitor.id)
        assert row.check_lease_token is None
        assert row.status is MonitorStatus.PENDING
        assert row.consecutive_failures == 0
        assert row.next_check_at > monitor.next_check_at
        assert await session.scalar(select(func.count()).select_from(CheckModel)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(IncidentModel)) == 0
        )
