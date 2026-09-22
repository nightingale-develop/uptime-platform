import json
import logging
from datetime import UTC, datetime
from uuid import uuid4

import httpx2
import pytest

from uptime_platform.notifications.entities import (
    NotificationDestination,
    NotificationDestinationType,
    SlackDestinationConfig,
)
from uptime_platform.notifications.exceptions import NotificationDeliveryError
from uptime_platform.notifications.factory import create_notification_channel
from uptime_platform.notifications.slack import SlackNotificationChannel
from uptime_platform.organizations.constants import DEFAULT_ORGANIZATION_ID
from uptime_platform.outbox.entities import OutboxEvent, OutboxEventType

pytestmark = pytest.mark.anyio
HOOK = "https://hooks.slack.com/services/T0123/B0456/secret-hook-value"
PUBLIC_URL = "https://uptime.example.com"


def make_event(event_type=OutboxEventType.INCIDENT_OPENED, **payload):
    return OutboxEvent(
        id=uuid4(),
        organization_id=DEFAULT_ORGANIZATION_ID,
        event_type=event_type,
        payload={"monitor_id": str(uuid4()), "incident_id": str(uuid4()), **payload},
        created_at=datetime.now(UTC),
        processed_at=None,
    )


async def send_and_capture(event, public_app_url=PUBLIC_URL):
    captured = []

    def handler(request):
        captured.append(request)
        return httpx2.Response(200, text="ok")

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        await SlackNotificationChannel(
            client=client,
            webhook_url=HOOK,
            timeout_seconds=5,
            public_app_url=public_app_url,
        ).send(event)
    assert len(captured) == 1
    assert captured[0].method == "POST"
    assert str(captured[0].url) == HOOK
    return json.loads(captured[0].content)


def section_text(body):
    sections = [block["text"] for block in body["blocks"] if block["type"] == "section"]
    assert sections
    assert all(item["type"] == "plain_text" for item in sections)
    assert all(0 < len(item["text"]) <= 3000 for item in sections)
    return "\n".join(item["text"] for item in sections)


async def test_slack_opened_incident_has_context_and_monitor_button():
    event = make_event(
        monitor_name="Production API",
        monitor_type="http",
        target="https://api.example.com/health",
        reason="HTTP 503 Service Unavailable",
        started_at="2026-09-20T14:32:00+00:00",
    )
    body = await send_and_capture(event)
    message = section_text(body)
    for expected in (
        "Incident opened",
        "Production API",
        "HTTP",
        "https://api.example.com/health",
        "HTTP 503 Service Unavailable",
        "20 Sep 2026, 14:32:00 UTC",
        event.payload["monitor_id"],
        event.payload["incident_id"],
    ):
        assert expected in message
    buttons = [
        element
        for block in body["blocks"]
        if block["type"] == "actions"
        for element in block["elements"]
    ]
    assert any(
        button["url"] == f"{PUBLIC_URL}/monitors/{event.payload['monitor_id']}"
        for button in buttons
    )
    assert body["unfurl_links"] is False
    assert body["unfurl_media"] is False


async def test_slack_resolved_incident_uses_real_timestamps_and_duration():
    body = await send_and_capture(
        make_event(
            OutboxEventType.INCIDENT_RESOLVED,
            monitor_name="API",
            started_at="2026-09-20T14:32:00+00:00",
            resolved_at="2026-09-20T14:36:32+00:00",
            duration_seconds=99999,
        )
    )
    message = section_text(body)
    assert "Incident resolved" in message
    assert "Downtime: 4 min 32 sec" in message
    assert "Started: 20 Sep 2026, 14:32:00 UTC" in message
    assert "Resolved: 20 Sep 2026, 14:36:32 UTC" in message
    assert "Reason:" not in message


async def test_slack_legacy_event_does_not_invent_context_or_localhost_link():
    body = await send_and_capture(make_event(), public_app_url="")
    message = section_text(body)
    assert "Monitor: Unknown" in message
    assert "reason unavailable" in message
    assert "View monitor" not in message
    assert all(block["type"] != "actions" for block in body["blocks"])
    assert "localhost" not in json.dumps(body)


@pytest.mark.parametrize("host", ["hooks.slack.com", "hooks.slack-gov.com"])
async def test_slack_escapes_mentions_and_redacts_monitor_secrets(host):
    event = make_event(
        monitor_name="<!channel> <@U123> & *API*",
        target="https://user:private-pass@api.example.com/health?api_key=private-query",
        reason=f"Failure at https://{host}/services/T0123/B0456/private-hook",
    )
    body = await send_and_capture(event)
    serialized = json.dumps(body)
    for secret in (
        "private-pass",
        "private-query",
        "private-hook",
        "secret-hook-value",
    ):
        assert secret not in serialized
    assert "<!channel>" in section_text(body)
    assert "<!channel>" not in body["text"]
    assert "<@U123>" not in body["text"]
    assert "&lt;!channel&gt;" in body["text"]
    assert body["mrkdwn"] is False
    assert body["parse"] == "none"


async def test_slack_long_content_respects_block_limits():
    body = await send_and_capture(
        make_event(
            monitor_name="A" * 10000,
            monitor_type="B" * 10000,
            target="C" * 10000,
            reason="D" * 10000,
        ),
        public_app_url="https://uptime.example.com/" + "a" * 1900,
    )
    section_text(body)
    assert len(body["blocks"]) <= 50


@pytest.mark.parametrize(
    ("status", "response_text"),
    [
        (400, "invalid_payload"),
        (403, "action_prohibited"),
        (429, "rate_limited"),
        (500, "error"),
        (200, "not_ok"),
        (204, ""),
    ],
)
async def test_slack_unsuccessful_responses_raise_secret_free_error(
    status, response_text
):
    def handler(request):
        return httpx2.Response(status, text=f"{response_text} {HOOK}")

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        with pytest.raises(NotificationDeliveryError) as error:
            await SlackNotificationChannel(client, HOOK, 5).send(make_event())
    assert "Slack" in str(error.value)
    assert HOOK not in str(error.value)
    assert "secret-hook-value" not in str(error.value)


async def test_slack_transport_failure_does_not_expose_webhook_url():
    def handler(request):
        raise httpx2.ConnectError(f"Failed to connect to {HOOK}", request=request)

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        with pytest.raises(NotificationDeliveryError) as error:
            await SlackNotificationChannel(client, HOOK, 5).send(make_event())
    assert HOOK not in str(error.value)
    assert "secret-hook-value" not in str(error.value)


@pytest.mark.parametrize("status", [200, 429])
async def test_slack_http_client_logs_preserve_status_without_credentials(
    caplog, status
):
    def handler(request):
        return httpx2.Response(status, text="ok" if status == 200 else "rate_limited")

    with caplog.at_level(logging.INFO, logger="httpx2"):
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler)
        ) as client:
            channel = SlackNotificationChannel(client, HOOK, 5)
            if status == 200:
                await channel.send(make_event())
            else:
                with pytest.raises(NotificationDeliveryError):
                    await channel.send(make_event())
    assert str(status) in caplog.text
    assert HOOK not in caplog.text
    assert "secret-hook-value" not in caplog.text


async def test_slack_never_follows_redirect_even_if_client_enables_it():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx2.Response(
            307, headers={"location": "https://attacker.example.com"}
        )

    async with httpx2.AsyncClient(
        transport=httpx2.MockTransport(handler), follow_redirects=True
    ) as client:
        with pytest.raises(NotificationDeliveryError):
            await SlackNotificationChannel(client, HOOK, 5).send(make_event())
    assert len(requests) == 1


async def test_factory_creates_slack_channel_and_passes_public_url():
    event = make_event()
    requests = []

    def handler(request):
        requests.append(request)
        return httpx2.Response(200, text="ok")

    destination = NotificationDestination(
        id=uuid4(),
        organization_id=DEFAULT_ORGANIZATION_ID,
        name="Slack",
        destination_type=NotificationDestinationType.SLACK,
        enabled=True,
        config=SlackDestinationConfig(HOOK),
        created_at=datetime.now(UTC),
    )
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        channel = create_notification_channel(destination, client, 5, PUBLIC_URL)
        assert isinstance(channel, SlackNotificationChannel)
        await channel.send(event)
    assert (
        f"{PUBLIC_URL}/monitors/{event.payload['monitor_id']}"
        in requests[0].content.decode()
    )
