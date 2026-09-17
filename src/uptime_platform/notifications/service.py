from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from uptime_platform.core.metrics import Metrics, get_metrics
from uptime_platform.notifications.entities import (
    NotificationDelivery,
)
from uptime_platform.notifications.exceptions import (
    NotificationDeliveryError,
)
from uptime_platform.notifications.protocols import (
    NotificationChannelProtocol,
)
from uptime_platform.notifications.repository_protocols import (
    NotificationDeliveryRepositoryProtocol,
    NotificationDestinationRepositoryProtocol,
)
from uptime_platform.outbox.entities import OutboxEvent
from uptime_platform.outbox.protocols import (
    OutboxRepositoryProtocol,
)


class NotificationService:
    def __init__(
        self,
        retry_base_seconds: int = 5,
        retry_max_seconds: int = 300,
        metrics: Metrics | None = None,
    ) -> None:
        self._metrics = metrics if metrics is not None else get_metrics("worker")
        self._retry_base_seconds = retry_base_seconds
        self._retry_max_seconds = retry_max_seconds

    async def process(
        self,
        delivery: NotificationDelivery,
        event: OutboxEvent,
        channel: NotificationChannelProtocol,
    ) -> NotificationDelivery:
        attempts = delivery.attempts + 1

        try:
            await channel.send(event)

        except NotificationDeliveryError as exc:
            self._metrics.deliveries.labels("failure").inc()
            now = datetime.now(UTC)

            return replace(
                delivery,
                attempts=attempts,
                last_error=str(exc)[:2000],
                next_attempt_at=(now + timedelta(seconds=self._retry_delay(attempts))),
                locked_until=None,
            )

        except BaseException:
            self._metrics.deliveries.labels("failure").inc()
            raise

        self._metrics.deliveries.labels("success").inc()
        return replace(
            delivery,
            processed_at=datetime.now(UTC),
            attempts=attempts,
            last_error=None,
            locked_until=None,
        )

    def _retry_delay(
        self,
        attempts: int,
    ) -> int:
        delay = self._retry_base_seconds * 2 ** (attempts - 1)

        return min(
            delay,
            self._retry_max_seconds,
        )


class NotificationFanoutService:
    def __init__(
        self,
        destination_repository: NotificationDestinationRepositoryProtocol,
        delivery_repository: NotificationDeliveryRepositoryProtocol,
        outbox_repository: OutboxRepositoryProtocol,
    ) -> None:
        self._destination_repository = destination_repository
        self._delivery_repository = delivery_repository
        self._outbox_repository = outbox_repository

    async def fan_out(
        self,
        event: OutboxEvent,
    ) -> list[NotificationDelivery]:
        destinations = await self._destination_repository.get_enabled(
            organization_id=event.organization_id,
        )

        now = datetime.now(UTC)

        created_deliveries: list[NotificationDelivery] = []

        for destination in destinations:
            delivery = NotificationDelivery(
                id=uuid4(),
                event_id=event.id,
                destination_id=destination.id,
                created_at=now,
                processed_at=None,
                attempts=0,
                last_error=None,
                next_attempt_at=now,
                locked_until=None,
            )

            created = await self._delivery_repository.create_if_missing(delivery)

            if created:
                created_deliveries.append(delivery)

        processed_event = replace(
            event,
            processed_at=now,
        )

        await self._outbox_repository.update(processed_event)

        return created_deliveries
