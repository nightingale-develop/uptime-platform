import logging
import re
from html import escape

import httpx2

from uptime_platform.notifications.content import notification_payload, text_message
from uptime_platform.notifications.exceptions import NotificationDeliveryError
from uptime_platform.outbox.entities import OutboxEvent


class _SlackWebhookLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = re.sub(
            r"(https://hooks\.slack(?:-gov)?\.com/services/)\S+",
            r"\1[redacted]",
            record.getMessage(),
        )
        record.args = ()
        return True


_slack_log_filter = _SlackWebhookLogFilter()


def validate_slack_webhook_url(value: str) -> str:
    if len(value) > 2048 or not re.fullmatch(
        r"https://hooks\.slack(?:-gov)?\.com/services/"
        r"[A-Za-z0-9_-]+/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+",
        value,
    ):
        raise ValueError("A valid Slack incoming webhook URL is required")
    return value


class SlackNotificationChannel:
    def __init__(
        self,
        client: httpx2.AsyncClient,
        webhook_url: str,
        timeout_seconds: int,
        public_app_url: str = "",
    ) -> None:
        self._client = client
        self._webhook_url = validate_slack_webhook_url(webhook_url)
        logging.getLogger("httpx2").addFilter(_slack_log_filter)
        self._timeout_seconds = timeout_seconds
        self._public_app_url = public_app_url

    async def send(self, event: OutboxEvent) -> None:
        message = text_message(event, self._public_app_url)
        blocks: list[dict[str, object]] = [
            {
                "type": "section",
                "text": {"type": "plain_text", "text": message[start : start + 3000]},
            }
            for start in range(0, len(message), 3000)
        ]
        monitor_url = notification_payload(event, self._public_app_url).get(
            "monitor_url"
        )
        if monitor_url:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "View monitor"},
                            "action_id": "view_monitor",
                            "url": monitor_url,
                        }
                    ],
                }
            )
        try:
            response = await self._client.post(
                self._webhook_url,
                json={
                    "text": escape(message, quote=False),
                    "blocks": blocks,
                    "mrkdwn": False,
                    "parse": "none",
                    "unfurl_links": False,
                    "unfurl_media": False,
                },
                timeout=self._timeout_seconds,
                follow_redirects=False,
            )
        except httpx2.RequestError:
            raise NotificationDeliveryError("Slack request failed") from None
        if response.status_code != 200:
            raise NotificationDeliveryError(
                f"Slack API returned HTTP {response.status_code}"
            )
        if response.text.strip() != "ok":
            raise NotificationDeliveryError("Slack did not confirm message delivery")
