import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from uptime_platform.checks.entities import CheckResult
from uptime_platform.checks.service import CheckService
from uptime_platform.monitors.entities import (
    HttpMonitorConfig,
    Monitor,
    MonitorClaim,
    MonitorStatus,
    MonitorType,
)
from uptime_platform.scheduler.scheduler import Scheduler

pytestmark = pytest.mark.anyio


class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def begin(self):
        return self


def make_claim(timeout_seconds=5):
    now = datetime.now(UTC)
    return MonitorClaim(
        monitor=Monitor(
            id=uuid4(),
            organization_id=uuid4(),
            name="Test",
            monitor_type=MonitorType.HTTP,
            config=HttpMonitorConfig(url="https://example.com"),
            interval_seconds=60,
            timeout_seconds=timeout_seconds,
            status=MonitorStatus.PENDING,
            created_at=now,
            next_check_at=now,
        ),
        token=uuid4(),
        expires_at=now + timedelta(seconds=30),
    )


@pytest.fixture
def setup_scheduler(monkeypatch):
    factory = MagicMock()
    factory.create.return_value.check = AsyncMock(
        return_value=CheckResult(True, 1, 200, None)
    )
    scheduler = Scheduler(
        session_factory=FakeSession,
        checker_factory=factory,
        batch_size=1,
    )
    release = AsyncMock()
    record = AsyncMock()
    monkeypatch.setattr(scheduler, "_release_claims", release)
    monkeypatch.setattr(CheckService, "record", record)
    return scheduler, factory, release, record


async def test_scheduler_records_with_claim_token(setup_scheduler, monkeypatch):
    scheduler, factory, release, record = setup_scheduler
    claim = make_claim()
    monkeypatch.setattr(scheduler, "_claim_monitors", AsyncMock(return_value=[claim]))

    assert await scheduler.run_once() == 1
    factory.create.assert_called_once_with(claim.monitor)
    record.assert_awaited_once_with(
        monitor_id=claim.monitor.id,
        result=factory.create.return_value.check.return_value,
        lease_token=claim.token,
        checked_monitor=claim.monitor,
    )
    release.assert_awaited_once_with([claim])


async def test_unexpected_checker_error_releases_claim(setup_scheduler, monkeypatch):
    scheduler, factory, release, record = setup_scheduler
    claim = make_claim()
    factory.create.side_effect = RuntimeError("checker failed")
    monkeypatch.setattr(scheduler, "_claim_monitors", AsyncMock(return_value=[claim]))

    assert await scheduler.run_once() == 1
    record.assert_not_awaited()
    release.assert_awaited_once_with([claim])


async def test_total_timeout_is_recorded_as_failed_check(setup_scheduler, monkeypatch):
    scheduler, factory, release, record = setup_scheduler
    claim = make_claim(timeout_seconds=0.01)

    async def stalled(**kwargs):
        await asyncio.Event().wait()

    factory.create.return_value.check.side_effect = stalled
    monkeypatch.setattr(scheduler, "_claim_monitors", AsyncMock(return_value=[claim]))

    async with asyncio.timeout(2):
        assert await scheduler.run_once() == 1
    result = record.await_args.kwargs["result"]
    assert not result.success
    assert "total timeout" in result.error
    release.assert_awaited_once_with([claim])


async def test_cancellation_drains_checker_before_cleanup(setup_scheduler, monkeypatch):
    scheduler, factory, release, record = setup_scheduler
    claim = make_claim()
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def stalled(**kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def cleanup(claims):
        assert cancelled.is_set()
        assert claims == [claim]

    factory.create.return_value.check.side_effect = stalled
    release.side_effect = cleanup
    monkeypatch.setattr(scheduler, "_claim_monitors", AsyncMock(return_value=[claim]))

    async with asyncio.timeout(2):
        task = asyncio.create_task(scheduler.run_once())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    record.assert_not_awaited()
    release.assert_awaited_once()


async def test_batch_is_claimed_in_capacity_sized_waves(monkeypatch):
    scheduler = Scheduler(FakeSession, batch_size=5, concurrency=2)
    waves = [[make_claim(), make_claim()], [make_claim(), make_claim()], [make_claim()]]
    observed = []

    async def claim(*, limit, exclude_ids):
        observed.append((limit, set(exclude_ids)))
        return waves[len(observed) - 1]

    monkeypatch.setattr(scheduler, "_claim_monitors", claim)
    monkeypatch.setattr(scheduler, "_check_monitor", AsyncMock())
    monkeypatch.setattr(scheduler, "_release_claims", AsyncMock())

    assert await scheduler.run_once() == 5
    assert [limit for limit, _ in observed] == [2, 2, 1]
    assert observed[1][1] == {c.monitor.id for c in waves[0]}
    assert len(observed[2][1]) == 4


async def test_polling_recovers_from_database_error(monkeypatch):
    scheduler = Scheduler(FakeSession)
    run_once = AsyncMock(side_effect=[RuntimeError("db unavailable"), 0])
    monkeypatch.setattr(scheduler, "run_once", run_once)
    sleep = AsyncMock(side_effect=[None, asyncio.CancelledError()])
    monkeypatch.setattr(asyncio, "sleep", sleep)

    with pytest.raises(asyncio.CancelledError):
        await scheduler.run_forever()
    assert run_once.await_count == 2


@pytest.mark.parametrize(
    "options",
    [
        {"concurrency": 0},
        {"batch_size": 0},
        {"lease_grace_seconds": 0},
        {"cleanup_timeout_seconds": 0},
        {"poll_interval_seconds": 0},
    ],
)
async def test_invalid_configuration_is_rejected(options):
    with pytest.raises(ValueError):
        Scheduler(FakeSession, **options)


@pytest.mark.parametrize("success", [True, False])
async def test_scheduler_metrics_include_failed_monitor_results(
    setup_scheduler, monkeypatch, success
):
    from uptime_platform.core.metrics import Metrics

    scheduler, factory, _release, _record = setup_scheduler
    metrics = Metrics("scheduler")
    scheduler._metrics = metrics
    factory.create.return_value.check.return_value = CheckResult(success, 1, 200, None)
    monkeypatch.setattr(
        scheduler, "_claim_monitors", AsyncMock(return_value=[make_claim()])
    )
    await scheduler.run_once()
    assert (
        metrics.registry.get_sample_value(
            "uptime_scheduler_last_success_timestamp_seconds"
        )
        > 0
    )
    assert (
        metrics.registry.get_sample_value(
            "uptime_checks_total",
            {"monitor_type": "http", "outcome": "success" if success else "failure"},
        )
        == 1
    )
    assert (
        metrics.registry.get_sample_value(
            "uptime_check_duration_seconds_count", {"monitor_type": "http"}
        )
        == 1
    )


@pytest.mark.parametrize("failure", ["claim", "check", "record", "release", "stale"])
async def test_failed_cycle_does_not_advance_success_timestamp(
    setup_scheduler, monkeypatch, failure
):
    from uptime_platform.core.metrics import Metrics

    scheduler, factory, release, record = setup_scheduler
    metrics = Metrics("scheduler")
    scheduler._metrics = metrics
    metrics.scheduler_success.set(123)
    claim = AsyncMock(return_value=[make_claim()])
    monkeypatch.setattr(scheduler, "_claim_monitors", claim)
    if failure == "claim":
        claim.side_effect = RuntimeError("database unavailable")
    elif failure == "check":
        factory.create.return_value.check.side_effect = RuntimeError("checker error")
    elif failure == "record":
        record.side_effect = RuntimeError("commit error")
    elif failure == "release":
        release.return_value = False
    else:
        record.return_value = None
    if failure == "claim":
        with pytest.raises(RuntimeError):
            await scheduler.run_once()
    else:
        await scheduler.run_once()
    assert (
        metrics.registry.get_sample_value(
            "uptime_scheduler_last_success_timestamp_seconds"
        )
        == 123
    )


async def test_empty_successful_cycle_updates_timestamp(setup_scheduler, monkeypatch):
    from uptime_platform.core.metrics import Metrics

    scheduler, *_ = setup_scheduler
    scheduler._metrics = Metrics("scheduler")
    monkeypatch.setattr(scheduler, "_claim_monitors", AsyncMock(return_value=[]))
    assert await scheduler.run_once() == 0
    assert (
        scheduler._metrics.registry.get_sample_value(
            "uptime_scheduler_last_success_timestamp_seconds"
        )
        > 0
    )
