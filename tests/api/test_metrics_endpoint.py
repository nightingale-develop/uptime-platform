from unittest.mock import AsyncMock

import httpx2
import pytest
from prometheus_client.parser import text_string_to_metric_families

from uptime_platform.core import metrics_router
from uptime_platform.main import app

pytestmark = pytest.mark.anyio


async def test_metrics_exposes_queue_without_authentication(monkeypatch):
    monkeypatch.setattr(
        metrics_router, "notification_queue_size", AsyncMock(return_value=(3, 7))
    )
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    families = {
        family.name: family for family in text_string_to_metric_families(response.text)
    }
    queue = families["uptime_notification_queue_size"]
    assert {sample.labels["stage"]: sample.value for sample in queue.samples} == {
        "fanout": 3,
        "delivery": 7,
    }


async def test_failed_queue_read_fails_scrape_instead_of_reporting_zero(monkeypatch):
    monkeypatch.setattr(
        metrics_router, "notification_queue_size", AsyncMock(side_effect=TimeoutError)
    )
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/metrics")
    assert response.status_code >= 500
    assert "uptime_notification_queue_size" not in response.text
