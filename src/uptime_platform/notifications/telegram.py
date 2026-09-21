import httpx2

from uptime_platform.notifications.content import text_message
from uptime_platform.notifications.exceptions import (
    NotificationDeliveryError,
)
from uptime_platform.outbox.entities import (
    OutboxEvent,
)


class TelegramNotificationChannel:
    def __init__(
        self,
        client: httpx2.AsyncClient,
        bot_token: str,
        chat_id: str,
        timeout_seconds: int,
        public_app_url: str = "",
    ) -> None:
        self._client = client
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._timeout_seconds = timeout_seconds
        self._public_app_url = public_app_url

    async def send(
        self,
        event: OutboxEvent,
    ) -> None:
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"

        try:
            response = await self._client.post(
                url,
                json={
                    "chat_id": self._chat_id,
                    "text": text_message(event, self._public_app_url),
                    "link_preview_options": {"is_disabled": True},
                },
                timeout=self._timeout_seconds,
            )
        except httpx2.RequestError as exc:
            raise NotificationDeliveryError("Telegram request failed") from exc

        if response.is_error:
            raise NotificationDeliveryError(
                f"Telegram API returned HTTP {response.status_code}"
            )
