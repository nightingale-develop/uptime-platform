import json
import socket
import ssl
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx2
import pytest

from uptime_platform.checks.entities import CheckResult
from uptime_platform.checks.failures import failure_kind
from uptime_platform.checks.http import HttpChecker
from uptime_platform.checks.tcp import TcpChecker
from uptime_platform.core.config import Settings
from uptime_platform.incidents.entities import Incident, IncidentStatus
from uptime_platform.monitors.entities import (
    DnsMonitorConfig,
    DnsRecordType,
    HttpMonitorConfig,
    IcmpMonitorConfig,
    Monitor,
    MonitorStatus,
    MonitorType,
    TcpMonitorConfig,
    TlsMonitorConfig,
)
from uptime_platform.notifications.content import (
    check_reason,
    html_message,
    incident_payload,
    notification_payload,
    public_app_url,
    text_message,
)
from uptime_platform.notifications.email import EmailNotificationChannel
from uptime_platform.notifications.entities import EmailSecurity
from uptime_platform.notifications.exceptions import NotificationDeliveryError
from uptime_platform.notifications.telegram import TelegramNotificationChannel
from uptime_platform.notifications.webhook import WebhookNotificationChannel
from uptime_platform.outbox.entities import OutboxEvent, OutboxEventType

NOW = datetime(2026, 9, 20, 14, 32, tzinfo=UTC)
BASE = "https://uptime.example.com"


def monitor() -> Monitor:
    return Monitor(
        id=uuid4(),
        organization_id=uuid4(),
        name='Production <API> & "health"',
        monitor_type=MonitorType.HTTP,
        config=HttpMonitorConfig(
            url="https://user:password-secret@api.example.com/health?arbitrary=query-secret#fragment-secret",
            body_contains="body-secret",
        ),
        interval_seconds=60,
        timeout_seconds=5,
        status=MonitorStatus.UP,
        created_at=NOW,
        next_check_at=NOW,
    )


def event(resolved: bool = False) -> OutboxEvent:
    target = monitor()
    incident = Incident(
        uuid4(),
        target.id,
        IncidentStatus.RESOLVED if resolved else IncidentStatus.OPEN,
        NOW,
        NOW + timedelta(seconds=272) if resolved else None,
    )
    result = CheckResult(
        resolved,
        10,
        200 if resolved else 503,
        None if resolved else "Unexpected HTTP status code: 503",
    )
    return OutboxEvent(
        uuid4(),
        target.organization_id,
        OutboxEventType.INCIDENT_RESOLVED
        if resolved
        else OutboxEventType.INCIDENT_OPENED,
        incident_payload(target, incident, result),
        NOW,
        None,
    )


def test_open_snapshot_and_all_formats_exclude_credentials_and_query_values():
    opened = event()
    text = text_message(opened, BASE)
    html = html_message(opened, BASE)
    payload = notification_payload(opened, BASE)
    assert "HTTP 503 Service Unavailable" in text
    assert "Production <API>" in text
    assert "Type: HTTP" in text
    assert "20 Sep 2026, 14:32:00 UTC" in text
    assert payload["target"] == "https://api.example.com/health"
    assert payload["monitor_url"] == f"{BASE}/monitors/{opened.payload['monitor_id']}"
    assert 'href="https://uptime.example.com/monitors/' in html
    assert "&lt;API&gt; &amp; &quot;health&quot;" in html
    assert "<API>" not in html
    for secret in (
        "password-secret",
        "query-secret",
        "fragment-secret",
        "body-secret",
        "user:",
    ):
        assert secret not in text + html + json.dumps(payload) + json.dumps(
            opened.payload
        )


def test_resolved_message_uses_incident_times_not_delivery_time():
    resolved = replace(event(True), created_at=NOW + timedelta(days=4))
    text = text_message(resolved, BASE)
    assert "🟢 Incident resolved" in text
    assert "Downtime: 4 min 32 sec" in text
    assert "Resolved: 20 Sep 2026, 14:36:32 UTC" in text
    assert "Reason:" not in text
    assert notification_payload(resolved, BASE)["duration_seconds"] == 272


@pytest.mark.parametrize("resolved", [False, True])
def test_legacy_event_does_not_invent_missing_data(resolved):
    source = event(resolved)
    legacy = replace(
        source,
        payload={key: source.payload[key] for key in ("monitor_id", "incident_id")},
    )
    text = text_message(legacy)
    assert "Monitor: Unknown" in text
    assert "Started: Unavailable" in text
    assert "View monitor" not in text
    assert ("Downtime: Unavailable" if resolved else "reason unavailable") in text
    assert notification_payload(legacy) == legacy.payload


@pytest.mark.parametrize(
    ("kind", "config", "target"),
    [
        (
            MonitorType.DNS,
            DnsMonitorConfig("example.com", DnsRecordType.A),
            "example.com",
        ),
        (MonitorType.TCP, TcpMonitorConfig("2001:db8::1", 443), "[2001:db8::1]:443"),
        (MonitorType.TLS, TlsMonitorConfig("example.com"), "example.com:443"),
        (MonitorType.ICMP, IcmpMonitorConfig("example.com"), "example.com"),
    ],
)
def test_monitor_target_formats(kind, config, target):
    item = replace(monitor(), monitor_type=kind, config=config)
    incident = Incident(uuid4(), item.id, IncidentStatus.OPEN, NOW, None)
    payload = incident_payload(item, incident, CheckResult(False, 1, None, None))
    assert payload["target"] == target
    assert payload["monitor_type"] == kind.value


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (TimeoutError(), "timeout"),
        (httpx2.ReadTimeout("token=secret"), "timeout"),
        (socket.gaierror("password=secret"), "dns"),
        (ssl.SSLCertVerificationError("private cert"), "tls_certificate"),
        (ssl.SSLError("private TLS data"), "tls"),
        (ConnectionRefusedError(), "connection_refused"),
        (httpx2.ConnectError("api_key=secret"), "connection"),
        (RuntimeError("token=unknown-secret"), "unknown"),
    ],
)
def test_exception_types_supply_safe_reason(error, kind):
    assert failure_kind(error) == kind
    result = CheckResult(False, 1, None, str(error), {"failure_kind": kind})
    reason = check_reason(result)
    assert "secret" not in reason and "private" not in reason
    assert reason


def test_nested_dns_cause_is_more_specific_than_http_connection_error():
    error = httpx2.ConnectError("hidden")
    error.__cause__ = socket.gaierror("hidden DNS query")
    assert failure_kind(error) == "dns"


def test_unknown_raw_error_is_not_sent_and_body_mismatch_is_preserved():
    assert (
        check_reason(CheckResult(False, 1, None, "opaque-private-value"))
        == "Check failed; reason unavailable"
    )
    assert (
        check_reason(
            CheckResult(False, 1, 200, "Expected text was not found in response body")
        )
        == "Expected text was not found in response body"
    )


@pytest.mark.parametrize(
    "value",
    [
        "http://localhost:8080",
        "http://frontend",
        "http://127.0.0.1",
        "http://10.0.0.1",
        "http://[::1]",
        "https://foo.internal",
        "https://a.localhost",
        "https://user:secret@example.com",
        "https://example.com?token=x",
        "javascript:alert(1)",
    ],
)
def test_public_url_rejects_internal_or_sensitive_urls(value):
    with pytest.raises(ValueError):
        public_app_url(value)
    with pytest.raises(ValueError):
        Settings(_env_file=None, database_url="unused", public_app_url=value)


def test_public_url_supports_external_base_path_and_optional_empty_setting():
    assert public_app_url(BASE + "/uptime/") == BASE + "/uptime"
    assert public_app_url("") == ""


@pytest.mark.parametrize(
    "value",
    ["http://127.1", "http://127.0.0.1.", "http://0177.0.0.1", "http://0x7f.0.0.1"],
)
def test_public_url_rejects_alternative_loopback_notation(value):
    with pytest.raises(ValueError):
        public_app_url(value)


@pytest.mark.parametrize(
    "value",
    [
        r"http://127.0.0.1\example.com",
        "http://%31%32%37.0.0.1",
        "http://127.0.0.1\x00.example.com",
        "http://bad_host.example.com",
    ],
)
def test_public_url_rejects_browser_host_parser_ambiguities(value):
    with pytest.raises(ValueError):
        public_app_url(value)


@pytest.mark.parametrize(
    "url",
    [
        "https://api.telegram.org/bot123456:SYNTHETIC_SECRET/getMe",
        "https://api.telegram.org/bot123456%3ASYNTHETIC_SECRET/getMe",
        "https://hooks.slack.com/services/T123/B123/SYNTHETIC_SECRET",
        "https://hooks.slack.com./services/T123/B123/SYNTHETIC_SECRET",
        "https://discord.com/api/webhooks/123/SYNTHETIC_SECRET",
        "https://example.com/api/token/SYNTHETIC_SECRET/status",
    ],
)
def test_known_credential_paths_are_redacted_before_snapshot(url):
    item = replace(monitor(), config=HttpMonitorConfig(url))
    incident = Incident(uuid4(), item.id, IncidentStatus.OPEN, NOW, None)
    payload = incident_payload(item, incident, CheckResult(False, 1, None, "unknown"))
    notification = replace(event(), payload=payload)
    for content in (
        json.dumps(payload),
        text_message(notification, BASE),
        html_message(notification, BASE),
        json.dumps(notification_payload(notification, BASE)),
    ):
        assert "SYNTHETIC_SECRET" not in content


def test_non_http_target_never_echoes_url_credentials():
    item = replace(
        monitor(),
        monitor_type=MonitorType.TCP,
        config=TcpMonitorConfig("user:password@host", 443),
    )
    incident = Incident(uuid4(), item.id, IncidentStatus.OPEN, NOW, None)
    payload = incident_payload(item, incident, CheckResult(False, 1, None, None))
    assert payload["target"] == "Unavailable"


@pytest.mark.parametrize(
    "name",
    [
        "Authorization: Bearer SYNTHETIC_TOKEN",
        "Authorization: Basic SYNTHETIC_TOKEN",
        "HTTPS://user:SYNTHETIC_PASS@example.com/health?x=SYNTHETIC_QUERY",
    ],
)
def test_monitor_name_redacts_authorization_and_uppercase_urls(name):
    item = replace(monitor(), name=name)
    incident = Incident(uuid4(), item.id, IncidentStatus.OPEN, NOW, None)
    payload = incident_payload(item, incident, CheckResult(False, 1, None, "unknown"))
    notification = replace(event(), payload=payload)
    serialized = (
        json.dumps(payload)
        + text_message(notification, BASE)
        + html_message(notification, BASE)
        + json.dumps(notification_payload(notification, BASE))
    )
    assert "SYNTHETIC_" not in serialized


@pytest.mark.parametrize(
    "date", ["0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00", "invalid", None]
)
def test_invalid_snapshot_dates_do_not_poison_delivery(date):
    notification = event(True)
    notification = replace(
        notification, payload={**notification.payload, "started_at": date}
    )
    assert "Started: Unavailable" in text_message(notification, BASE)
    assert notification_payload(notification, BASE)["duration_seconds"] is None


@pytest.mark.anyio
async def test_timeout_checkers_capture_reason_even_when_exception_text_is_empty(
    monkeypatch,
):
    async def fail(*args, **kwargs):
        raise TimeoutError

    monkeypatch.setattr("uptime_platform.checks.tcp.asyncio.open_connection", fail)
    result = await TcpChecker("example.com", 443).check(1)
    assert check_reason(result) == "Check timed out"
    original = httpx2.AsyncClient

    async def timeout(request):
        raise httpx2.ReadTimeout("", request=request)

    monkeypatch.setattr(
        "uptime_platform.checks.http.httpx2.AsyncClient",
        lambda **kw: original(transport=httpx2.MockTransport(timeout), **kw),
    )
    result = await HttpChecker("https://example.com").check(1)
    assert check_reason(result) == "Check timed out"


@pytest.mark.anyio
@pytest.mark.parametrize("resolved", [False, True])
async def test_channels_deliver_enriched_plain_html_and_structured_json(
    monkeypatch, resolved
):
    opened = event(resolved)
    captured = []

    def handler(request):
        captured.append(request)
        return httpx2.Response(200, json={"ok": True})

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        await TelegramNotificationChannel(client, "bot-secret", "chat", 5, BASE).send(
            opened
        )
        await WebhookNotificationChannel(
            client, "https://hook.example.com", "signing-secret", 5, BASE
        ).send(opened)
    telegram = json.loads(captured[0].content)
    webhook = json.loads(captured[1].content)
    assert "parse_mode" not in telegram
    assert "Production <API>" in telegram["text"]
    assert webhook["payload"]["status_code"] == (200 if resolved else 503)
    if resolved:
        assert webhook["payload"]["duration_seconds"] == 272
        assert "Downtime: 4 min 32 sec" in telegram["text"]
    assert webhook["payload"]["monitor_name"] == opened.payload["monitor_name"]
    assert "bot-secret" not in telegram["text"]
    assert "signing-secret" not in captured[1].content.decode()
    messages = []

    async def send(message, **kwargs):
        messages.append(message)
        return {}, "OK"

    monkeypatch.setattr("uptime_platform.notifications.email.aiosmtplib.send", send)
    await EmailNotificationChannel(
        "smtp",
        25,
        None,
        "smtp-secret",
        "from@example.com",
        "to@example.com",
        EmailSecurity.NONE,
        5,
        BASE,
    ).send(opened)
    assert messages[0].get_content_type() == "multipart/alternative"
    assert "&lt;API&gt;" in messages[0].get_body(preferencelist=("html",)).get_content()
    assert "smtp-secret" not in messages[0].as_string()


@pytest.mark.anyio
async def test_webhook_transport_failure_does_not_persist_destination_secret():
    def fail(request):
        raise httpx2.ConnectError(f"Failed {request.url}", request=request)

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(fail)) as client:
        channel = WebhookNotificationChannel(
            client, "https://user:secret@example.com?token=hidden", "signing", 5
        )
        with pytest.raises(
            NotificationDeliveryError, match="^Webhook delivery failed$"
        ):
            await channel.send(event())
