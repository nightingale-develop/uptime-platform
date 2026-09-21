import json
from datetime import UTC, datetime

import httpx2

from uptime_platform.notifications.content import notification_payload
from uptime_platform.notifications.exceptions import (
    NotificationDeliveryError,
)
from uptime_platform.notifications.signing import (
    create_webhook_signature,
)
from uptime_platform.outbox.entities import OutboxEvent


class WebhookNotificationChannel:
    def __init__(
        self,
        client: httpx2.AsyncClient,
        url: str,
        secret: str,
        timeout_seconds: float,
        public_app_url: str = "",
    ) -> None:
        self._client = client
        self._url = url
        self._secret = secret
        self._timeout_seconds = timeout_seconds
        self._public_app_url = public_app_url

    async def send(
        self,
        event: OutboxEvent,
    ) -> None:
        payload = {
            "id": str(event.id),
            "type": event.event_type.value,
            "created_at": event.created_at.isoformat(),
            "payload": notification_payload(event, self._public_app_url),
        }

        body = json.dumps(
            payload,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

        timestamp = str(int(datetime.now(UTC).timestamp()))

        signature = create_webhook_signature(
            secret=self._secret,
            timestamp=timestamp,
            body=body,
        )

        try:
            response = await self._client.post(
                self._url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Uptime-Event-ID": str(event.id),
                    "X-Uptime-Timestamp": timestamp,
                    "X-Uptime-Signature": signature,
                },
                timeout=self._timeout_seconds,
            )

            response.raise_for_status()

        except httpx2.HTTPError as exc:
            raise NotificationDeliveryError("Webhook delivery failed") from exc
