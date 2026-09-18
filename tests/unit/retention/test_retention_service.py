import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from uptime_platform.core.config import Settings
from uptime_platform.retention import service as module
from uptime_platform.retention.service import RetentionService

pytestmark = pytest.mark.anyio


async def test_disabled_retention_never_opens_database():
    factory = Mock(side_effect=AssertionError("must not open a connection"))
    settings = Settings(_env_file=None, database_url="unused", retention_enabled=False)
    service = RetentionService(factory, settings)
    assert await service.run_once() == {}
    await service.run_forever()
    factory.assert_not_called()


async def test_periodic_cleanup_recovers_after_failure_and_stops_on_cancellation(
    monkeypatch,
    caplog,
):
    settings = Settings(
        _env_file=None, database_url="unused", retention_interval_seconds=17
    )
    service = RetentionService(Mock(), settings)
    cleanup = AsyncMock(side_effect=[RuntimeError("unavailable"), {"checks": 2}])
    monkeypatch.setattr(service, "run_once", cleanup)
    intervals = []

    async def sleep(seconds):
        intervals.append(seconds)
        if len(intervals) == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(module.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await service.run_forever()
    assert cleanup.await_count == 2
    assert intervals == [17, 17]
    assert "retention cleanup failed" in caplog.text


@pytest.mark.parametrize(
    "name",
    [
        "retention_checks_days",
        "retention_incidents_days",
        "retention_notifications_days",
        "retention_interval_seconds",
        "retention_batch_size",
    ],
)
@pytest.mark.parametrize("value", [0, -1])
async def test_retention_limits_must_be_positive(name, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="unused", **{name: value})
