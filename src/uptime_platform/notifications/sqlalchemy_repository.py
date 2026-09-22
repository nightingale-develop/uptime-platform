from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from uptime_platform.notifications.entities import (
    EmailDestinationConfig,
    EmailSecurity,
    NotificationDelivery,
    NotificationDestination,
    NotificationDestinationConfig,
    NotificationDestinationType,
    SlackDestinationConfig,
    TelegramDestinationConfig,
    WebhookDestinationConfig,
)
from uptime_platform.notifications.models import (
    NotificationDeliveryModel,
    NotificationDestinationModel,
)


class SqlAlchemyNotificationDestinationRepository:
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def create(
        self,
        destination: NotificationDestination,
    ) -> NotificationDestination:
        model = NotificationDestinationModel(
            id=destination.id,
            organization_id=destination.organization_id,
            name=destination.name,
            destination_type=destination.destination_type,
            enabled=destination.enabled,
            config=self._config_to_dict(destination.config),
            created_at=destination.created_at,
        )

        self._session.add(model)

        await self._session.flush()
        await self._session.refresh(model)

        return self._to_entity(model)

    async def get_by_id(
        self,
        destination_id: UUID,
        organization_id: UUID,
    ) -> NotificationDestination | None:
        statement = select(NotificationDestinationModel).where(
            NotificationDestinationModel.id == destination_id,
            NotificationDestinationModel.organization_id == organization_id,
        )

        result = await self._session.execute(statement)

        model = result.scalar_one_or_none()

        if model is None:
            return None

        return self._to_entity(model)

    async def get_all(
        self,
        organization_id: UUID,
    ) -> list[NotificationDestination]:
        statement = (
            select(NotificationDestinationModel)
            .where(NotificationDestinationModel.organization_id == organization_id)
            .order_by(NotificationDestinationModel.created_at)
        )

        result = await self._session.execute(statement)

        return [self._to_entity(model) for model in result.scalars().all()]

    async def update(
        self,
        destination: NotificationDestination,
    ) -> NotificationDestination | None:
        statement = select(NotificationDestinationModel).where(
            NotificationDestinationModel.id == destination.id,
            NotificationDestinationModel.organization_id == destination.organization_id,
        )

        result = await self._session.execute(statement)

        model = result.scalar_one_or_none()

        if model is None:
            return None

        model.name = destination.name
        model.destination_type = destination.destination_type
        model.enabled = destination.enabled
        model.config = self._config_to_dict(destination.config)

        await self._session.flush()
        await self._session.refresh(model)

        return self._to_entity(model)

    async def delete(
        self,
        destination_id: UUID,
        organization_id: UUID,
    ) -> bool:
        statement = select(NotificationDestinationModel).where(
            NotificationDestinationModel.id == destination_id,
            NotificationDestinationModel.organization_id == organization_id,
        )

        result = await self._session.execute(statement)

        model = result.scalar_one_or_none()

        if model is None:
            return False

        await self._session.delete(model)
        await self._session.flush()

        return True

    async def get_enabled(
        self,
        organization_id: UUID,
    ) -> list[NotificationDestination]:
        statement = (
            select(NotificationDestinationModel)
            .where(
                NotificationDestinationModel.organization_id == organization_id,
                NotificationDestinationModel.enabled.is_(True),
            )
            .order_by(NotificationDestinationModel.created_at)
        )

        result = await self._session.execute(statement)

        return [self._to_entity(model) for model in result.scalars().all()]

    @staticmethod
    def _to_entity(
        model: NotificationDestinationModel,
    ) -> NotificationDestination:
        if model.destination_type is NotificationDestinationType.WEBHOOK:
            config = WebhookDestinationConfig(
                url=model.config["url"],
                secret=model.config["secret"],
            )

        elif model.destination_type is NotificationDestinationType.TELEGRAM:
            config = TelegramDestinationConfig(
                bot_token=model.config["bot_token"],
                chat_id=model.config["chat_id"],
            )

        elif model.destination_type is NotificationDestinationType.SLACK:
            config = SlackDestinationConfig(webhook_url=model.config["webhook_url"])

        elif model.destination_type is NotificationDestinationType.EMAIL:
            config = EmailDestinationConfig(
                host=model.config["host"],
                port=model.config["port"],
                username=model.config.get("username"),
                password=model.config.get("password"),
                from_email=model.config["from_email"],
                to_email=model.config["to_email"],
                security=EmailSecurity(model.config["security"]),
            )

        else:
            raise ValueError(
                f"Unsupported notification destination type: {model.destination_type}"
            )

        return NotificationDestination(
            id=model.id,
            organization_id=model.organization_id,
            name=model.name,
            destination_type=model.destination_type,
            enabled=model.enabled,
            config=config,
            created_at=model.created_at,
        )

    @staticmethod
    def _config_to_dict(
        config: NotificationDestinationConfig,
    ) -> dict[str, str | int | None]:
        if isinstance(
            config,
            WebhookDestinationConfig,
        ):
            return {
                "url": config.url,
                "secret": config.secret,
            }

        if isinstance(
            config,
            TelegramDestinationConfig,
        ):
            return {
                "bot_token": config.bot_token,
                "chat_id": config.chat_id,
            }

        if isinstance(
            config,
            EmailDestinationConfig,
        ):
            return {
                "host": config.host,
                "port": config.port,
                "username": config.username,
                "password": config.password,
                "from_email": config.from_email,
                "to_email": config.to_email,
                "security": config.security.value,
            }

        if isinstance(config, SlackDestinationConfig):
            return {"webhook_url": config.webhook_url}

        raise TypeError(f"Unsupported destination config: {type(config)}")


class SqlAlchemyNotificationDeliveryRepository:
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def create(
        self,
        delivery: NotificationDelivery,
    ) -> NotificationDelivery:
        model = NotificationDeliveryModel(
            id=delivery.id,
            event_id=delivery.event_id,
            destination_id=delivery.destination_id,
            created_at=delivery.created_at,
            processed_at=delivery.processed_at,
            attempts=delivery.attempts,
            last_error=delivery.last_error,
            next_attempt_at=delivery.next_attempt_at,
            locked_until=delivery.locked_until,
            lease_token=delivery.lease_token,
        )

        self._session.add(model)

        await self._session.flush()
        await self._session.refresh(model)

        return self._to_entity(model)

    async def get_by_id(
        self,
        delivery_id: UUID,
    ) -> NotificationDelivery | None:
        model = await self._session.get(
            NotificationDeliveryModel,
            delivery_id,
        )

        if model is None:
            return None

        return self._to_entity(model)

    async def claim_pending(
        self,
        *,
        limit: int,
        max_attempts: int,
        lease_seconds: float,
        exclude_ids: set[UUID] | None = None,
    ) -> list[NotificationDelivery]:
        if limit < 1 or max_attempts < 1 or lease_seconds <= 0:
            raise ValueError("Claim limits and lease duration must be positive")
        statement = (
            select(NotificationDeliveryModel)
            .where(
                NotificationDeliveryModel.processed_at.is_(None),
                NotificationDeliveryModel.attempts < max_attempts,
                NotificationDeliveryModel.next_attempt_at <= func.clock_timestamp(),
                or_(
                    NotificationDeliveryModel.locked_until.is_(None),
                    NotificationDeliveryModel.locked_until <= func.clock_timestamp(),
                ),
            )
            .order_by(
                NotificationDeliveryModel.next_attempt_at, NotificationDeliveryModel.id
            )
            .limit(limit)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        if exclude_ids:
            statement = statement.where(
                NotificationDeliveryModel.id.not_in(exclude_ids)
            )
        models = (await self._session.scalars(statement)).all()
        if models:
            now = await self._session.scalar(select(func.clock_timestamp()))
            for model in models:
                model.locked_until = now + timedelta(seconds=lease_seconds)
                model.lease_token = uuid4()
            await self._session.flush()
        return [self._to_entity(model) for model in models]

    async def remaining_lease_seconds(
        self, delivery_id: UUID, lease_token: UUID
    ) -> float | None:
        if lease_token is None:
            return None
        value = await self._session.scalar(
            select(
                func.extract(
                    "epoch",
                    NotificationDeliveryModel.locked_until - func.clock_timestamp(),
                )
            ).where(
                NotificationDeliveryModel.id == delivery_id,
                NotificationDeliveryModel.lease_token == lease_token,
                NotificationDeliveryModel.processed_at.is_(None),
            )
        )
        return float(value) if value is not None and value > 0 else None

    async def update(
        self,
        delivery: NotificationDelivery,
        *,
        lease_token: UUID,
    ) -> NotificationDelivery | None:
        if lease_token is None:
            return None
        model = await self._session.scalar(
            select(NotificationDeliveryModel)
            .where(NotificationDeliveryModel.id == delivery.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if model is None:
            return None
        now = await self._session.scalar(select(func.clock_timestamp()))
        if (
            model.lease_token != lease_token
            or model.locked_until is None
            or model.locked_until <= now
            or model.processed_at is not None
        ):
            return None
        model.processed_at = delivery.processed_at
        model.attempts = delivery.attempts
        model.last_error = delivery.last_error
        model.next_attempt_at = delivery.next_attempt_at
        model.locked_until = None
        model.lease_token = None
        await self._session.flush()
        return self._to_entity(model)

    async def create_if_missing(
        self,
        delivery: NotificationDelivery,
    ) -> bool:
        statement = (
            insert(NotificationDeliveryModel)
            .values(
                id=delivery.id,
                event_id=delivery.event_id,
                destination_id=delivery.destination_id,
                created_at=delivery.created_at,
                processed_at=delivery.processed_at,
                attempts=delivery.attempts,
                last_error=delivery.last_error,
                next_attempt_at=delivery.next_attempt_at,
                locked_until=delivery.locked_until,
                lease_token=delivery.lease_token,
            )
            .on_conflict_do_nothing(
                constraint=("uq_notification_delivery_event_destination")
            )
            .returning(NotificationDeliveryModel.id)
        )

        result = await self._session.execute(statement)

        created_id = result.scalar_one_or_none()

        return created_id is not None

    async def release_lock(
        self,
        delivery_id: UUID,
        lease_token: UUID,
    ) -> bool:
        if lease_token is None:
            return False
        statement = (
            update(NotificationDeliveryModel)
            .where(
                NotificationDeliveryModel.id == delivery_id,
                NotificationDeliveryModel.lease_token == lease_token,
            )
            .values(
                locked_until=None,
                lease_token=None,
            )
            .returning(NotificationDeliveryModel.id)
        )

        result = await self._session.execute(statement)

        released_id = result.scalar_one_or_none()

        return released_id is not None

    @staticmethod
    def _to_entity(
        model: NotificationDeliveryModel,
    ) -> NotificationDelivery:
        return NotificationDelivery(
            id=model.id,
            event_id=model.event_id,
            destination_id=model.destination_id,
            created_at=model.created_at,
            processed_at=model.processed_at,
            attempts=model.attempts,
            last_error=model.last_error,
            next_attempt_at=model.next_attempt_at,
            locked_until=model.locked_until,
            lease_token=model.lease_token,
        )
