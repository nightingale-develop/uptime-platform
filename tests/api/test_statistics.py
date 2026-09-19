from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx2
import pytest

from uptime_platform.main import app
from uptime_platform.statistics.dependencies import get_statistics_service
from uptime_platform.statistics.entities import MonitorStatistics

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("has_checks", [True, False])
async def test_partial_statistics_exposes_available_dates(has_checks):
    monitor_id = uuid4()
    end = datetime(2026, 6, 1, tzinfo=UTC)
    start = end - timedelta(days=90)
    first = end - timedelta(days=29) if has_checks else None
    last = end - timedelta(minutes=1) if has_checks else None
    service = Mock()
    service.get_monitor_statistics = AsyncMock(
        return_value=MonitorStatistics(
            monitor_id=monitor_id,
            starts_at=start,
            ends_at=end,
            total_checks=2 if has_checks else 0,
            successful_checks=2 if has_checks else 0,
            failed_checks=0,
            uptime_percentage=100.0 if has_checks else None,
            average_response_time_ms=1.0 if has_checks else None,
            history_available_from=first,
            first_check_at=first,
            last_check_at=last,
            is_partial=True,
        )
    )
    app.dependency_overrides[get_statistics_service] = lambda: service
    try:
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                f"/api/v1/monitors/{monitor_id}/statistics",
                params={"starts_at": start.isoformat(), "ends_at": end.isoformat()},
            )
    finally:
        app.dependency_overrides.pop(get_statistics_service, None)

    assert response.status_code == 200
    data = response.json()
    assert data["is_partial"] is True
    assert data["period"] is None
    assert datetime.fromisoformat(data["starts_at"]) == start
    assert datetime.fromisoformat(data["ends_at"]) == end
    assert data["uptime_percentage"] == (100.0 if has_checks else None)
    for name, expected in (
        ("history_available_from", first),
        ("first_check_at", first),
        ("last_check_at", last),
    ):
        assert (datetime.fromisoformat(data[name]) if data[name] else None) == expected
