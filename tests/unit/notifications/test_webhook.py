import hashlib
import hmac
import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx2
import pytest

from uptime_platform.notifications.exceptions import (
    NotificationDeliveryError,
)
from uptime_platform.notifications.webhook import (
    WebhookNotificationChannel,
)
from uptime_platform.organizations.constants import DEFAULT_ORGANIZATION_ID
from uptime_platform.outbox.entities import (
    OutboxEvent,
    OutboxEventType,
)

pytestmark = pytest.mark.anyio


def make_event() -> OutboxEvent:
    now = datetime.now(UTC)

    return OutboxEvent(
        id=uuid4(),
        organization_id=DEFAULT_ORGANIZATION_ID,
        event_type=OutboxEventType.INCIDENT_OPENED,
        payload={
            "incident_id": str(uuid4()),
            "monitor_id": str(uuid4()),
        },
        created_at=now,
        processed_at=None,
    )


async def test_webhook_sends_signed_event() -> None:
    event = make_event()
    secret = "test-secret"

    captured_request: httpx2.Request | None = None

    def handler(
        request: httpx2.Request,
    ) -> httpx2.Response:
        nonlocal captured_request

        captured_request = request

        return httpx2.Response(status_code=204)

    transport = httpx2.MockTransport(handler)

    async with httpx2.AsyncClient(transport=transport) as client:
        channel = WebhookNotificationChannel(
            client=client,
            url="https://example.com/webhook",
            secret=secret,
            timeout_seconds=5,
        )

        await channel.send(event)

    assert captured_request is not None

    assert captured_request.method == "POST"

    assert str(captured_request.url) == "https://example.com/webhook"

    assert captured_request.headers["X-Uptime-Event-ID"] == str(event.id)

    timestamp = captured_request.headers["X-Uptime-Timestamp"]

    signature = captured_request.headers["X-Uptime-Signature"]

    signed_payload = timestamp.encode("utf-8") + b"." + captured_request.content

    expected_signature = (
        "sha256="
        + hmac.new(
            key=secret.encode("utf-8"),
            msg=signed_payload,
            digestmod=hashlib.sha256,
        ).hexdigest()
    )

    assert hmac.compare_digest(
        signature,
        expected_signature,
    )

    body = json.loads(captured_request.content)

    assert body["id"] == str(event.id)

    assert body["type"] == ("incident_opened")

    assert body["payload"] == (event.payload)


async def test_webhook_http_error_raises_delivery_error() -> None:
    event = make_event()

    def handler(
        request: httpx2.Request,
    ) -> httpx2.Response:
        return httpx2.Response(status_code=500)

    transport = httpx2.MockTransport(handler)

    async with httpx2.AsyncClient(transport=transport) as client:
        channel = WebhookNotificationChannel(
            client=client,
            url="https://example.com/webhook",
            secret="test-secret",
            timeout_seconds=5,
        )

        with pytest.raises(NotificationDeliveryError):
            await channel.send(event)


async def test_webhook_retries_keep_stable_event_id():
    event = make_event()
    requests = []

    def handler(request):
        requests.append(request)
        return httpx2.Response(status_code=503 if len(requests) == 1 else 204)

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        channel = WebhookNotificationChannel(
            client, "https://example.com/webhook", "test-secret", 5
        )
        with pytest.raises(NotificationDeliveryError):
            await channel.send(event)
        await channel.send(event)
    assert [request.headers["X-Uptime-Event-ID"] for request in requests] == [
        str(event.id)
    ] * 2
    assert all(
        json.loads(request.content)["id"] == str(event.id) for request in requests
    )
