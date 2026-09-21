import re
from datetime import UTC, datetime
from html import escape
from http import HTTPStatus
from ipaddress import ip_address
from urllib.parse import unquote, urlsplit, urlunsplit
from uuid import UUID

from uptime_platform.checks.entities import CheckResult
from uptime_platform.incidents.entities import Incident
from uptime_platform.monitors.entities import HttpMonitorConfig, Monitor
from uptime_platform.outbox.entities import OutboxEvent, OutboxEventType

REASONS = {
    "timeout": "Check timed out",
    "dns": "DNS resolution failed",
    "tls_certificate": "TLS certificate verification failed",
    "tls": "TLS handshake failed",
    "connection_refused": "Connection refused",
    "connection": "Connection failed",
    "redirects": "Too many HTTP redirects",
    "protocol": "HTTP protocol error",
    "unknown": "Check failed; reason unavailable",
}


def safe_path(path: str, host: str) -> str:
    parts = path.split("/")
    hide_rest = False
    for index, part in enumerate(parts):
        decoded = unquote(part)
        if hide_rest:
            parts[index] = "[redacted]" if part else ""
        elif re.match(r"(?i)^bot\d+:", decoded):
            parts[index] = "bot[redacted]"
        elif decoded.lower() in {
            "token",
            "tokens",
            "secret",
            "password",
            "api-key",
            "api_key",
            "apikey",
            "webhook",
            "webhooks",
        } or (host.lower().rstrip(".") == "hooks.slack.com" and decoded == "services"):
            hide_rest = True
        elif re.search(r"(?i)(?:token|secret|password|api[_-]?key)=", decoded) or (
            len(decoded) >= 24
            and re.fullmatch(r"[A-Za-z0-9_+=.:-]+", decoded)
            and re.search(r"\d", decoded)
        ):
            parts[index] = "[redacted]"
    return "/".join(parts)


def safe_url(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        host = parsed.hostname
        if ":" in host:
            host = f"[{host}]"
        authority = f"{host}:{parsed.port}" if parsed.port else host
        return urlunsplit(
            (parsed.scheme, authority, safe_path(parsed.path, parsed.hostname), "", "")
        )
    except ValueError:
        return None


def safe_text(value: object, limit: int = 400) -> str:
    if not isinstance(value, str):
        return "Unknown"
    value = re.sub(
        r"(?i)https?://[^\s<>\"']+", lambda m: safe_url(m[0]) or "[redacted URL]", value
    )
    value = re.sub(r"(?i)\b(bearer|basic)\s+[a-z0-9+/=_\-.]+", r"\1 [redacted]", value)
    value = re.sub(
        r"(?i)\b(password|passwd|token|api[_-]?key|secret|authorization)\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)",
        r"\1=[redacted]",
        value,
    )
    value = " ".join(value.split())
    return value[:limit] or "Unknown"


def public_app_url(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").rstrip(".")
        if (
            safe_url(value) is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or any(char.isspace() for char in value)
            or "\\" in value
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
            or len(value) > 2048
            or safe_path(parsed.path, host) != parsed.path
            or host.lower().rstrip(".").endswith((".localhost", ".local", ".internal"))
            or host.lower().rstrip(".") == "localhost"
        ):
            raise ValueError(
                "PUBLIC_APP_URL must be a public HTTP(S) URL without credentials, query or fragment"
            )
        try:
            address = ip_address(host)
        except ValueError:
            try:
                ascii_host = host.encode("idna").decode("ascii")
            except UnicodeError:
                raise ValueError("PUBLIC_APP_URL hostname is invalid") from None
            if len(ascii_host) > 253 or not re.fullmatch(
                r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",
                ascii_host,
                re.IGNORECASE,
            ):
                raise ValueError("PUBLIC_APP_URL hostname is invalid")
            if "." not in host or all(
                re.fullmatch(r"(?:\d+|0x[0-9a-f]+)", label, re.IGNORECASE)
                for label in host.split(".")
            ):
                raise ValueError("PUBLIC_APP_URL must use a public hostname") from None
        else:
            if not address.is_global:
                raise ValueError("PUBLIC_APP_URL must not use an internal IP address")
    except ValueError:
        raise ValueError(
            "PUBLIC_APP_URL must be a public HTTP(S) URL without credentials, query or fragment"
        ) from None
    return value.rstrip("/")


def check_reason(result: CheckResult) -> str:
    error = result.error or ""
    if error in {
        "Expected text was not found in response body",
        "No ICMP reply received",
        "TLS connection has no SSL object",
        "TLS certificate expiration date is missing",
    }:
        return error
    if error == "Check exceeded its total timeout":
        return REASONS["timeout"]
    if re.fullmatch(r"TLS certificate expires in \d+ days", error):
        return error
    kind = (result.details or {}).get("failure_kind")
    if isinstance(kind, str) and kind in REASONS and kind != "unknown":
        return REASONS[kind]
    if result.status_code is not None:
        try:
            phrase = HTTPStatus(result.status_code).phrase
        except ValueError:
            phrase = "Unexpected status"
        return f"HTTP {result.status_code} {phrase}"
    return REASONS["unknown"]


def incident_payload(
    monitor: Monitor, incident: Incident, result: CheckResult
) -> dict[str, object]:
    if isinstance(monitor.config, HttpMonitorConfig):
        target = safe_text(safe_url(monitor.config.url))
    else:
        host = safe_text(monitor.config.host, 255)
        if not re.fullmatch(r"[\w.:%-]+", host):
            host = "Unavailable"
        port = getattr(monitor.config, "port", None)
        target = (
            f"{'[' + host + ']' if ':' in host else host}:{port}"
            if port and host != "Unavailable"
            else host
        )
    resolved = incident.resolved_at
    return {
        "monitor_id": str(monitor.id),
        "incident_id": str(incident.id),
        "monitor_name": safe_text(monitor.name, 100),
        "monitor_type": monitor.monitor_type.value,
        "target": target,
        "started_at": incident.started_at.isoformat(),
        "resolved_at": resolved.isoformat() if resolved else None,
        "duration_seconds": max(
            0, int((resolved - incident.started_at).total_seconds())
        )
        if resolved
        else None,
        "reason": check_reason(result) if not result.success else None,
        "status_code": result.status_code,
    }


def timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.astimezone(UTC) if parsed.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


def notification_payload(event: OutboxEvent, base_url: str = "") -> dict[str, object]:
    source = event.payload
    payload: dict[str, object] = {}
    for key in ("monitor_id", "incident_id"):
        try:
            payload[key] = str(UUID(str(source.get(key))))
        except (ValueError, TypeError, AttributeError):
            payload[key] = "unknown"
    if set(source) <= {"monitor_id", "incident_id"} and not base_url:
        return payload
    for key in ("monitor_name", "monitor_type", "target", "reason"):
        payload[key] = (
            safe_text(source.get(key)) if source.get(key) is not None else None
        )
    for key in ("started_at", "resolved_at"):
        parsed = timestamp(source.get(key))
        payload[key] = parsed.isoformat() if parsed else None
    started = timestamp(payload["started_at"])
    resolved = timestamp(payload["resolved_at"])
    payload["duration_seconds"] = (
        max(0, int((resolved - started).total_seconds()))
        if started and resolved
        else None
    )
    status = source.get("status_code")
    payload["status_code"] = (
        status if type(status) is int and 100 <= status <= 599 else None
    )
    payload["monitor_url"] = (
        f"{public_app_url(base_url)}/monitors/{payload['monitor_id']}"
        if base_url and payload["monitor_id"] != "unknown"
        else None
    )
    return payload


def event_title(event: OutboxEvent) -> str:
    return (
        "Incident opened"
        if event.event_type is OutboxEventType.INCIDENT_OPENED
        else "Incident resolved"
    )


def event_rows(event: OutboxEvent, base_url: str) -> list[tuple[str, str]]:
    payload = notification_payload(event, base_url)
    rows = [
        ("Monitor", str(payload.get("monitor_name") or "Unknown")),
        ("Type", str(payload.get("monitor_type") or "Unknown").upper()),
        ("Target", str(payload.get("target") or "Unavailable")),
    ]
    if event.event_type is OutboxEventType.INCIDENT_OPENED:
        rows.append(("Reason", str(payload.get("reason") or REASONS["unknown"])))
    else:
        duration = payload.get("duration_seconds")
        if isinstance(duration, int):
            days, remainder = divmod(duration, 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, seconds = divmod(remainder, 60)
            parts = [(days, "d"), (hours, "h"), (minutes, "min"), (seconds, "sec")]
            downtime = " ".join(
                f"{number} {unit}" for number, unit in parts if number or unit == "sec"
            )
        else:
            downtime = "Unavailable"
        rows.append(("Downtime", downtime))
    for key, label in (("started_at", "Started"), ("resolved_at", "Resolved")):
        if key == "resolved_at" and event.event_type is OutboxEventType.INCIDENT_OPENED:
            continue
        value = timestamp(payload.get(key))
        rows.append(
            (
                label,
                value.strftime("%d %b %Y, %H:%M:%S UTC") if value else "Unavailable",
            )
        )
    if payload.get("monitor_url"):
        rows.append(("View monitor", str(payload["monitor_url"])))
    rows.extend(
        (label, str(payload[key]))
        for key, label in (("monitor_id", "Monitor ID"), ("incident_id", "Incident ID"))
    )
    return rows


def text_message(event: OutboxEvent, base_url: str = "") -> str:
    icon = "🔴" if event.event_type is OutboxEventType.INCIDENT_OPENED else "🟢"
    return f"{icon} {event_title(event)}\n\n" + "\n".join(
        f"{label}: {value}" for label, value in event_rows(event, base_url)
    )


def html_message(event: OutboxEvent, base_url: str = "") -> str:
    rows = []
    for label, value in event_rows(event, base_url):
        content = escape(value)
        if label == "View monitor":
            content = f'<a href="{escape(value, quote=True)}">View monitor</a>'
        rows.append(f"<p><strong>{escape(label)}:</strong> {content}</p>")
    return f"<h2>{escape(event_title(event))}</h2>" + "".join(rows)
