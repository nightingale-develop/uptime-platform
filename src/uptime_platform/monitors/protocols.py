from datetime import datetime
from typing import Protocol
from uuid import UUID

from uptime_platform.monitors.entities import Monitor, MonitorClaim


class MonitorRepositoryProtocol(Protocol):
    async def create(
        self,
        monitor: Monitor,
    ) -> Monitor: ...

    async def get_all(
        self,
        organization_id: UUID,
    ) -> list[Monitor]: ...

    async def get_by_id(
        self,
        monitor_id: UUID,
        organization_id: UUID,
    ) -> Monitor | None: ...

    async def update(
        self,
        monitor: Monitor,
    ) -> Monitor | None: ...

    async def delete(
        self,
        monitor_id: UUID,
        organization_id: UUID,
    ) -> bool: ...

    async def get_due(
        self,
        now: datetime,
        limit: int,
    ) -> list[Monitor]: ...

    async def get_by_id_for_update(
        self,
        monitor_id: UUID,
        *,
        organization_id: UUID | None = None,
        lease_token: UUID | None = None,
    ) -> Monitor | None: ...

    async def release_check_lease(self, monitor_id: UUID, token: UUID) -> bool: ...

    async def claim_due(
        self,
        *,
        limit: int,
        lease_grace_seconds: float,
        exclude_ids: set[UUID] | None = None,
    ) -> list[MonitorClaim]: ...
