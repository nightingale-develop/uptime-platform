from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from uptime_platform.notifications.entities import (
    EmailDestinationConfig,
    NotificationDestination,
    NotificationDestinationConfig,
    SlackDestinationConfig,
    TelegramDestinationConfig,
    WebhookDestinationConfig,
)
from uptime_platform.notifications.repository_protocols import (
    NotificationDestinationRepositoryProtocol,
)
from uptime_platform.notifications.schemas import (
    EmailDestinationConfigCreate,
    EmailDestinationConfigUpdate,
    NotificationDestinationCreate,
    NotificationDestinationUpdate,
    SlackDestinationConfigCreate,
    SlackDestinationConfigUpdate,
    TelegramDestinationConfigCreate,
    TelegramDestinationConfigUpdate,
    WebhookDestinationConfigCreate,
    WebhookDestinationConfigUpdate,
)


def _create_config(
    config: (
        WebhookDestinationConfigCreate
        | TelegramDestinationConfigCreate
        | EmailDestinationConfigCreate
        | SlackDestinationConfigCreate
    ),
) -> NotificationDestinationConfig:
    if isinstance(
        config,
        WebhookDestinationConfigCreate,
    ):
        return WebhookDestinationConfig(
            url=str(config.url),
            secret=config.secret,
        )

    if isinstance(
        config,
        TelegramDestinationConfigCreate,
    ):
        return TelegramDestinationConfig(
            bot_token=config.bot_token,
            chat_id=config.chat_id,
        )

    if isinstance(
        config,
        EmailDestinationConfigCreate,
    ):
        return EmailDestinationConfig(
            host=config.host,
            port=config.port,
            username=config.username,
            password=config.password,
            from_email=str(config.from_email),
            to_email=str(config.to_email),
            security=config.security,
        )

    if isinstance(config, SlackDestinationConfigCreate):
        return SlackDestinationConfig(webhook_url=config.webhook_url)

    raise TypeError(f"Unsupported destination config: {type(config)}")


def _update_config(
    current: NotificationDestinationConfig,
    update: (
        WebhookDestinationConfigUpdate
        | TelegramDestinationConfigUpdate
        | EmailDestinationConfigUpdate
        | SlackDestinationConfigUpdate
    ),
) -> NotificationDestinationConfig:
    if isinstance(
        current,
        WebhookDestinationConfig,
    ) and isinstance(
        update,
        WebhookDestinationConfigUpdate,
    ):
        return WebhookDestinationConfig(
            url=(str(update.url) if update.url is not None else current.url),
            secret=(update.secret if update.secret is not None else current.secret),
        )

    if isinstance(
        current,
        TelegramDestinationConfig,
    ) and isinstance(
        update,
        TelegramDestinationConfigUpdate,
    ):
        return TelegramDestinationConfig(
            bot_token=(
                update.bot_token if update.bot_token is not None else current.bot_token
            ),
            chat_id=(update.chat_id if update.chat_id is not None else current.chat_id),
        )

    if isinstance(current, EmailDestinationConfig) and isinstance(
        update, EmailDestinationConfigUpdate
    ):
        return EmailDestinationConfig(
            host=(update.host if update.host is not None else current.host),
            port=(update.port if update.port is not None else current.port),
            username=(
                update.username
                if "username" in update.model_fields_set
                else current.username
            ),
            password=(
                update.password
                if "password" in update.model_fields_set
                else current.password
            ),
            from_email=(
                str(update.from_email)
                if update.from_email is not None
                else current.from_email
            ),
            to_email=(
                str(update.to_email)
                if update.to_email is not None
                else current.to_email
            ),
            security=(
                update.security if update.security is not None else current.security
            ),
        )

    if isinstance(current, SlackDestinationConfig) and isinstance(
        update, SlackDestinationConfigUpdate
    ):
        return SlackDestinationConfig(
            webhook_url=update.webhook_url or current.webhook_url
        )

    raise ValueError("Destination config type does not match destination type")


class NotificationDestinationService:
    def __init__(
        self,
        repository: NotificationDestinationRepositoryProtocol,
        organization_id: UUID,
    ) -> None:
        self._repository = repository
        self._organization_id = organization_id

    async def create(
        self,
        data: NotificationDestinationCreate,
    ) -> NotificationDestination:
        destination = NotificationDestination(
            id=uuid4(),
            organization_id=self._organization_id,
            name=data.name,
            destination_type=data.destination_type,
            enabled=data.enabled,
            config=_create_config(data.config),
            created_at=datetime.now(UTC),
        )

        return await self._repository.create(destination)

    async def get_all(
        self,
    ) -> list[NotificationDestination]:
        return await self._repository.get_all(self._organization_id)

    async def get_by_id(
        self,
        destination_id: UUID,
    ) -> NotificationDestination | None:
        return await self._repository.get_by_id(
            destination_id,
            self._organization_id,
        )

    async def update(
        self,
        destination_id: UUID,
        data: NotificationDestinationUpdate,
    ) -> NotificationDestination | None:
        destination = await self._repository.get_by_id(
            destination_id,
            self._organization_id,
        )

        if destination is None:
            return None

        config = destination.config

        if data.config is not None and data.config.model_fields_set:
            config = _update_config(
                current=destination.config,
                update=data.config,
            )

        updated_destination = replace(
            destination,
            name=(data.name if data.name is not None else destination.name),
            enabled=(data.enabled if data.enabled is not None else destination.enabled),
            config=config,
        )

        return await self._repository.update(updated_destination)

    async def delete(
        self,
        destination_id: UUID,
    ) -> bool:
        return await self._repository.delete(
            destination_id,
            self._organization_id,
        )
