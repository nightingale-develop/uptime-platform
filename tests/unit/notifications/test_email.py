from datetime import UTC, datetime
from email.message import EmailMessage
from uuid import uuid4

import pytest
from aiosmtplib.errors import SMTPException

import uptime_platform.notifications.email as email_module
from uptime_platform.notifications.email import (
    EmailNotificationChannel,
)
from uptime_platform.notifications.entities import (
    EmailSecurity,
)
from uptime_platform.notifications.exceptions import (
    NotificationDeliveryError,
)
from uptime_platform.organizations.constants import DEFAULT_ORGANIZATION_ID
from uptime_platform.outbox.entities import (
    OutboxEvent,
    OutboxEventType,
)

pytestmark = pytest.mark.anyio


def make_event() -> OutboxEvent:
    return OutboxEvent(
        id=uuid4(),
        organization_id=DEFAULT_ORGANIZATION_ID,
        event_type=OutboxEventType.INCIDENT_OPENED,
        payload={
            "incident_id": str(uuid4()),
            "monitor_id": str(uuid4()),
        },
        created_at=datetime.now(UTC),
        processed_at=None,
    )


async def test_email_sends_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = make_event()

    captured_message: EmailMessage | None = None
    captured_kwargs: dict[str, object] = {}

    async def fake_send(
        message: EmailMessage,
        **kwargs: object,
    ) -> tuple[dict, str]:
        nonlocal captured_message
        nonlocal captured_kwargs

        captured_message = message
        captured_kwargs = kwargs

        return {}, "OK"

    monkeypatch.setattr(
        email_module.aiosmtplib,
        "send",
        fake_send,
    )

    channel = EmailNotificationChannel(
        host="smtp.example.com",
        port=587,
        username="uptime@example.com",
        password="test-password",
        from_email="uptime@example.com",
        to_email="admin@example.com",
        security=EmailSecurity.STARTTLS,
        timeout_seconds=5,
    )

    await channel.send(event)

    assert captured_message is not None

    assert captured_message["From"] == "uptime@example.com"
    assert captured_message["To"] == "admin@example.com"
    assert captured_message["Subject"] == ("[Uptime Platform] Incident opened")

    body = captured_message.get_body(preferencelist=("plain",)).get_content()

    assert "Incident opened" in body
    assert event.payload["monitor_id"] in body
    assert event.payload["incident_id"] in body

    assert captured_kwargs["hostname"] == "smtp.example.com"
    assert captured_kwargs["port"] == 587
    assert captured_kwargs["username"] == "uptime@example.com"
    assert captured_kwargs["password"] == "test-password"
    assert captured_kwargs["sender"] == "uptime@example.com"
    assert captured_kwargs["recipients"] == ["admin@example.com"]
    assert captured_kwargs["timeout"] == 5
    assert captured_kwargs["use_tls"] is False
    assert captured_kwargs["start_tls"] is True


async def test_email_smtp_error_raises_delivery_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = make_event()

    async def fake_send(
        message: EmailMessage,
        **kwargs: object,
    ) -> tuple[dict, str]:
        raise SMTPException("SMTP failed")

    monkeypatch.setattr(
        email_module.aiosmtplib,
        "send",
        fake_send,
    )

    channel = EmailNotificationChannel(
        host="smtp.example.com",
        port=587,
        username="uptime@example.com",
        password="test-password",
        from_email="uptime@example.com",
        to_email="admin@example.com",
        security=EmailSecurity.STARTTLS,
        timeout_seconds=5,
    )

    with pytest.raises(NotificationDeliveryError):
        await channel.send(event)
