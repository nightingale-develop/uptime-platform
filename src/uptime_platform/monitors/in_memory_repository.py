from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from uptime_platform.monitors.entities import (
    Monitor,
    MonitorClaim,
    MonitorStatus,
)


class InMemoryMonitorRepository:
    def __init__(self) -> None:
        self._claims: dict[UUID, MonitorClaim] = {}
        self._monitors: dict[
            UUID,
            Monitor,
        ] = {}

    async def create(
        self,
        monitor: Monitor,
    ) -> Monitor:
        self._monitors[monitor.id] = monitor

        return monitor

    async def get_all(
        self,
        organization_id: UUID,
    ) -> list[Monitor]:
        return [
            monitor
            for monitor in self._monitors.values()
            if monitor.organization_id == organization_id
        ]

    async def get_by_id(
        self,
        monitor_id: UUID,
        organization_id: UUID,
    ) -> Monitor | None:
        monitor = self._monitors.get(monitor_id)

        if monitor is None:
            return None

        if monitor.organization_id != organization_id:
            return None

        return monitor

    async def get_by_id_for_update(
        self,
        monitor_id: UUID,
        *,
        organization_id: UUID | None = None,
        lease_token: UUID | None = None,
    ) -> Monitor | None:
        if lease_token is not None:
            claim = self._claims.get(monitor_id)
            if (
                claim is None
                or claim.token != lease_token
                or claim.expires_at <= datetime.now(UTC)
            ):
                return None
        monitor = self._monitors.get(monitor_id)
        if (
            monitor is not None
            and organization_id is not None
            and monitor.organization_id != organization_id
        ):
            return None
        return monitor

    async def claim_due(
        self,
        *,
        limit: int,
        lease_grace_seconds: float,
        exclude_ids: set[UUID] | None = None,
    ) -> list[MonitorClaim]:
        if limit < 1 or lease_grace_seconds <= 0:
            raise ValueError("Claim limit and lease grace must be positive")
        now = datetime.now(UTC)
        due = sorted(
            (
                monitor
                for monitor in self._monitors.values()
                if monitor.next_check_at <= now
                and monitor.status is not MonitorStatus.PAUSED
                and monitor.id not in (exclude_ids or set())
                and (
                    monitor.id not in self._claims
                    or self._claims[monitor.id].expires_at <= now
                )
            ),
            key=lambda monitor: (monitor.next_check_at, monitor.id),
        )
        claims = [
            MonitorClaim(
                monitor=monitor,
                token=uuid4(),
                expires_at=now
                + timedelta(seconds=monitor.timeout_seconds + lease_grace_seconds),
            )
            for monitor in due[:limit]
        ]
        for claim in claims:
            self._claims[claim.monitor.id] = claim
        return claims

    async def release_check_lease(self, monitor_id: UUID, token: UUID) -> bool:
        claim = self._claims.get(monitor_id)
        if claim is None or claim.token != token:
            return False
        del self._claims[monitor_id]
        return True

    async def update(
        self,
        monitor: Monitor,
    ) -> Monitor | None:
        if monitor.id not in self._monitors:
            return None

        self._monitors[monitor.id] = monitor

        return monitor

    async def delete(
        self,
        monitor_id: UUID,
        organization_id: UUID,
    ) -> bool:
        monitor = self._monitors.get(monitor_id)

        if monitor is None:
            return False

        if monitor.organization_id != organization_id:
            return False

        del self._monitors[monitor_id]
        self._claims.pop(monitor_id, None)

        return True

    async def get_due(
        self,
        now: datetime,
        limit: int,
    ) -> list[Monitor]:
        monitors = [
            monitor
            for monitor in self._monitors.values()
            if (
                monitor.next_check_at <= now
                and monitor.status is not MonitorStatus.PAUSED
            )
        ]

        monitors.sort(key=lambda monitor: monitor.next_check_at)

        return monitors[:limit]
