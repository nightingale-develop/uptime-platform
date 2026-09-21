import httpx2

from uptime_platform.notifications.email import (
    EmailNotificationChannel,
)
from uptime_platform.notifications.entities import (
    EmailDestinationConfig,
    NotificationDestination,
    NotificationDestinationType,
    TelegramDestinationConfig,
    WebhookDestinationConfig,
)
from uptime_platform.notifications.protocols import (
    NotificationChannelProtocol,
)
from uptime_platform.notifications.telegram import (
    TelegramNotificationChannel,
)
from uptime_platform.notifications.webhook import (
    WebhookNotificationChannel,
)


def create_notification_channel(
    destination: NotificationDestination,
    client: httpx2.AsyncClient,
    timeout_seconds: int,
    public_app_url: str = "",
) -> NotificationChannelProtocol:
    if destination.destination_type is NotificationDestinationType.WEBHOOK:
        if not isinstance(
            destination.config,
            WebhookDestinationConfig,
        ):
            raise TypeError("Webhook destination has invalid config")

        return WebhookNotificationChannel(
            client=client,
            url=destination.config.url,
            secret=destination.config.secret,
            timeout_seconds=timeout_seconds,
            public_app_url=public_app_url,
        )

    if destination.destination_type is NotificationDestinationType.TELEGRAM:
        if not isinstance(
            destination.config,
            TelegramDestinationConfig,
        ):
            raise TypeError("Telegram destination has invalid config")

        return TelegramNotificationChannel(
            client=client,
            bot_token=destination.config.bot_token,
            chat_id=destination.config.chat_id,
            timeout_seconds=timeout_seconds,
            public_app_url=public_app_url,
        )

    if destination.destination_type is NotificationDestinationType.EMAIL:
        if not isinstance(
            destination.config,
            EmailDestinationConfig,
        ):
            raise TypeError("Email destination has invalid config")

        return EmailNotificationChannel(
            host=destination.config.host,
            port=destination.config.port,
            username=destination.config.username,
            password=destination.config.password,
            from_email=destination.config.from_email,
            to_email=destination.config.to_email,
            security=destination.config.security,
            timeout_seconds=timeout_seconds,
            public_app_url=public_app_url,
        )

    raise ValueError(
        f"Unsupported notification destination type: {destination.destination_type}"
    )
