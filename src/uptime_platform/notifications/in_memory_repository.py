from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from uptime_platform.notifications.entities import (
    NotificationDelivery,
    NotificationDestination,
)


class InMemoryNotificationDestinationRepository:
    def __init__(self) -> None:
        self._destinations: dict[
            UUID,
            NotificationDestination,
        ] = {}

    async def create(
        self,
        destination: NotificationDestination,
    ) -> NotificationDestination:
        self._destinations[destination.id] = destination

        return destination

    async def get_by_id(
        self,
        destination_id: UUID,
        organization_id: UUID,
    ) -> NotificationDestination | None:
        destination = self._destinations.get(destination_id)

        if destination is None:
            return None

        if destination.organization_id != organization_id:
            return None

        return destination

    async def get_all(
        self,
        organization_id: UUID,
    ) -> list[NotificationDestination]:
        return [
            destination
            for destination in self._destinations.values()
            if (destination.organization_id == organization_id)
        ]

    async def update(
        self,
        destination: NotificationDestination,
    ) -> NotificationDestination | None:
        existing = self._destinations.get(destination.id)

        if existing is None:
            return None

        if existing.organization_id != destination.organization_id:
            return None

        self._destinations[destination.id] = destination

        return destination

    async def delete(
        self,
        destination_id: UUID,
        organization_id: UUID,
    ) -> bool:
        destination = self._destinations.get(destination_id)

        if destination is None:
            return False

        if destination.organization_id != organization_id:
            return False

        del self._destinations[destination_id]

        return True

    async def get_enabled(
        self,
        organization_id: UUID,
    ) -> list[NotificationDestination]:
        return [
            destination
            for destination in self._destinations.values()
            if (destination.organization_id == organization_id and destination.enabled)
        ]


class InMemoryNotificationDeliveryRepository:
    def __init__(self) -> None:
        self._deliveries: dict[
            UUID,
            NotificationDelivery,
        ] = {}

    async def create(
        self,
        delivery: NotificationDelivery,
    ) -> NotificationDelivery:
        self._deliveries[delivery.id] = delivery

        return delivery

    async def get_by_id(
        self,
        delivery_id: UUID,
    ) -> NotificationDelivery | None:
        return self._deliveries.get(delivery_id)

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
        now = datetime.now(UTC)
        locked_until = now + timedelta(seconds=lease_seconds)
        deliveries = [
            delivery
            for delivery in self._deliveries.values()
            if (
                delivery.id not in (exclude_ids or set())
                and delivery.processed_at is None
                and delivery.attempts < max_attempts
                and delivery.next_attempt_at <= now
                and (delivery.locked_until is None or delivery.locked_until <= now)
            )
        ]

        deliveries.sort(key=lambda delivery: (delivery.next_attempt_at, delivery.id))

        deliveries = deliveries[:limit]

        claimed = []

        for delivery in deliveries:
            claimed_delivery = replace(
                delivery,
                locked_until=locked_until,
                lease_token=uuid4(),
            )

            self._deliveries[delivery.id] = claimed_delivery

            claimed.append(claimed_delivery)

        return claimed

    async def update(
        self,
        delivery: NotificationDelivery,
        *,
        lease_token: UUID,
    ) -> NotificationDelivery | None:
        if await self.remaining_lease_seconds(delivery.id, lease_token) is None:
            return None

        updated = replace(delivery, locked_until=None, lease_token=None)
        self._deliveries[delivery.id] = updated
        return updated

    async def remaining_lease_seconds(
        self, delivery_id: UUID, lease_token: UUID
    ) -> float | None:
        delivery = self._deliveries.get(delivery_id)
        if (
            delivery is None
            or lease_token is None
            or delivery.lease_token != lease_token
            or delivery.locked_until is None
            or delivery.processed_at is not None
        ):
            return None
        remaining = (delivery.locked_until - datetime.now(UTC)).total_seconds()
        return remaining if remaining > 0 else None

    async def create_if_missing(
        self,
        delivery: NotificationDelivery,
    ) -> bool:
        already_exists = any(
            existing.event_id == delivery.event_id
            and existing.destination_id == delivery.destination_id
            for existing in self._deliveries.values()
        )

        if already_exists:
            return False

        self._deliveries[delivery.id] = delivery

        return True

    async def release_lock(
        self,
        delivery_id: UUID,
        lease_token: UUID,
    ) -> bool:
        delivery = self._deliveries.get(delivery_id)

        if delivery is None:
            return False

        if lease_token is None or delivery.lease_token != lease_token:
            return False

        self._deliveries[delivery_id] = replace(
            delivery,
            locked_until=None,
            lease_token=None,
        )

        return True
