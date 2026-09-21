from email.message import EmailMessage

import aiosmtplib
from aiosmtplib.errors import SMTPException

from uptime_platform.notifications.content import (
    event_title,
    html_message,
    text_message,
)
from uptime_platform.notifications.entities import (
    EmailSecurity,
)
from uptime_platform.notifications.exceptions import (
    NotificationDeliveryError,
)
from uptime_platform.outbox.entities import (
    OutboxEvent,
)


class EmailNotificationChannel:
    def __init__(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        from_email: str,
        to_email: str,
        security: EmailSecurity,
        timeout_seconds: int,
        public_app_url: str = "",
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from_email = from_email
        self._to_email = to_email
        self._security = security
        self._timeout_seconds = timeout_seconds
        self._public_app_url = public_app_url

    async def send(
        self,
        event: OutboxEvent,
    ) -> None:
        message = self._build_message(event)

        use_tls = self._security is EmailSecurity.TLS
        start_tls = self._security is EmailSecurity.STARTTLS

        try:
            recipient_errors, _ = await aiosmtplib.send(
                message,
                sender=self._from_email,
                recipients=[self._to_email],
                hostname=self._host,
                port=self._port,
                username=self._username,
                password=self._password,
                timeout=self._timeout_seconds,
                use_tls=use_tls,
                start_tls=start_tls,
            )

        except (SMTPException, OSError) as exc:
            raise NotificationDeliveryError("Email delivery failed") from exc

        if recipient_errors:
            raise NotificationDeliveryError("Email recipient was rejected")

    def _build_message(
        self,
        event: OutboxEvent,
    ) -> EmailMessage:
        title = event_title(event)
        message = EmailMessage()
        message["From"] = self._from_email
        message["To"] = self._to_email
        message["Subject"] = f"[Uptime Platform] {title}"
        message.set_content(text_message(event, self._public_app_url))
        message.add_alternative(
            html_message(event, self._public_app_url), subtype="html"
        )
        return message
