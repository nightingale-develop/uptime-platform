from typing import Protocol
from uuid import UUID

from uptime_platform.notifications.entities import (
    NotificationDelivery,
    NotificationDestination,
)


class NotificationDestinationRepositoryProtocol(Protocol):
    async def create(
        self,
        destination: NotificationDestination,
    ) -> NotificationDestination: ...

    async def get_by_id(
        self,
        destination_id: UUID,
        organization_id: UUID,
    ) -> NotificationDestination | None: ...

    async def get_all(
        self,
        organization_id: UUID,
    ) -> list[NotificationDestination]: ...

    async def delete(
        self,
        destination_id: UUID,
        organization_id: UUID,
    ) -> bool: ...

    async def update(
        self,
        destination: NotificationDestination,
    ) -> NotificationDestination | None: ...

    async def get_enabled(
        self,
        organization_id: UUID,
    ) -> list[NotificationDestination]: ...


class NotificationDeliveryRepositoryProtocol(Protocol):
    async def create(
        self,
        delivery: NotificationDelivery,
    ) -> NotificationDelivery: ...

    async def get_by_id(
        self,
        delivery_id: UUID,
    ) -> NotificationDelivery | None: ...

    async def claim_pending(
        self,
        *,
        limit: int,
        max_attempts: int,
        lease_seconds: float,
        exclude_ids: set[UUID] | None = None,
    ) -> list[NotificationDelivery]: ...

    async def remaining_lease_seconds(
        self, delivery_id: UUID, lease_token: UUID
    ) -> float | None: ...

    async def update(
        self,
        delivery: NotificationDelivery,
        *,
        lease_token: UUID,
    ) -> NotificationDelivery | None: ...

    async def create_if_missing(
        self,
        delivery: NotificationDelivery,
    ) -> bool: ...

    async def release_lock(
        self,
        delivery_id: UUID,
        lease_token: UUID,
    ) -> bool: ...
