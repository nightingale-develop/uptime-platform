import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from uptime_platform.core.metrics import Metrics
from uptime_platform.notifications.entities import NotificationDelivery
from uptime_platform.notifications.worker import NotificationWorker

pytestmark = pytest.mark.anyio


def make_delivery():
    now = datetime.now(UTC)
    return NotificationDelivery(
        id=uuid4(),
        event_id=uuid4(),
        destination_id=uuid4(),
        created_at=now,
        processed_at=None,
        attempts=0,
        last_error=None,
        next_attempt_at=now,
        locked_until=now + timedelta(seconds=60),
        lease_token=uuid4(),
    )


@pytest.mark.parametrize("result", [True, False])
async def test_cycle_cleans_all_claims_and_only_marks_successful_cycle(result):
    metrics = Metrics("worker")
    worker = NotificationWorker(
        MagicMock(), MagicMock(), concurrency=2, batch_size=3, metrics=metrics
    )
    deliveries = [make_delivery() for _ in range(3)]
    worker._fan_out_pending_events = AsyncMock(return_value=0)
    worker._claim_deliveries = AsyncMock(side_effect=[deliveries[:2], deliveries[2:]])
    worker._process_delivery = AsyncMock(return_value=result)
    worker._release_claims = AsyncMock(return_value=True)
    assert await worker.run_once() == (0, 3)
    assert [
        call.kwargs["limit"] for call in worker._claim_deliveries.await_args_list
    ] == [2, 1]
    assert worker._release_claims.await_count == 2
    assert (
        metrics.registry.get_sample_value(
            "uptime_notification_worker_last_success_timestamp_seconds"
        )
        > 0
    ) == result


async def test_unexpected_error_is_not_reclaimed_in_same_cycle():
    worker = NotificationWorker(MagicMock(), MagicMock(), batch_size=2)
    delivery = make_delivery()
    worker._fan_out_pending_events = AsyncMock(return_value=0)
    worker._claim_deliveries = AsyncMock(side_effect=[[delivery], []])
    worker._process_delivery = AsyncMock(side_effect=RuntimeError("boom"))
    worker._release_claims = AsyncMock(return_value=True)
    assert await worker.run_once() == (0, 1)
    assert worker._claim_deliveries.await_args.kwargs["exclude_ids"] == {delivery.id}
    worker._release_claims.assert_awaited_once_with([delivery])


async def test_cancellation_drains_senders_before_release():
    worker = NotificationWorker(MagicMock(), MagicMock(), concurrency=2)
    worker._fan_out_pending_events = AsyncMock(return_value=0)
    worker._claim_deliveries = AsyncMock(
        return_value=[make_delivery(), make_delivery()]
    )
    started = asyncio.Event()
    active = 0

    async def process(delivery):
        nonlocal active
        active += 1
        if active == 2:
            started.set()
        try:
            await asyncio.Event().wait()
        finally:
            active -= 1

    async def release(deliveries):
        assert active == 0
        assert len(deliveries) == 2
        return True

    worker._process_delivery = process
    worker._release_claims = AsyncMock(side_effect=release)
    async with asyncio.timeout(2):
        task = asyncio.create_task(worker.run_once())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    worker._release_claims.assert_awaited_once()


async def test_cleanup_failure_does_not_mark_cycle_successful():
    metrics = Metrics("worker")
    worker = NotificationWorker(MagicMock(), MagicMock(), batch_size=1, metrics=metrics)
    worker._fan_out_pending_events = AsyncMock(return_value=0)
    worker._claim_deliveries = AsyncMock(return_value=[make_delivery()])
    worker._process_delivery = AsyncMock(return_value=True)
    worker._release_claims = AsyncMock(return_value=False)
    await worker.run_once()
    assert (
        metrics.registry.get_sample_value(
            "uptime_notification_worker_last_success_timestamp_seconds"
        )
        == 0
    )


async def test_idle_successful_cycle_updates_timestamp():
    metrics = Metrics("worker")
    worker = NotificationWorker(MagicMock(), MagicMock(), metrics=metrics)
    worker._fan_out_pending_events = AsyncMock(return_value=0)
    worker._claim_deliveries = AsyncMock(return_value=[])
    assert await worker.run_once() == (0, 0)
    assert (
        metrics.registry.get_sample_value(
            "uptime_notification_worker_last_success_timestamp_seconds"
        )
        > 0
    )


@pytest.mark.parametrize(
    "parameter",
    [
        "concurrency",
        "batch_size",
        "lease_seconds",
        "max_attempts",
        "notification_timeout_seconds",
        "database_timeout_seconds",
        "cleanup_timeout_seconds",
        "poll_interval_seconds",
    ],
)
async def test_invalid_limits_are_rejected(parameter):
    with pytest.raises(ValueError):
        NotificationWorker(MagicMock(), MagicMock(), **{parameter: 0})
