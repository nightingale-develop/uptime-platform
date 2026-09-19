from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

from uptime_platform.monitors.protocols import (
    MonitorRepositoryProtocol,
)
from uptime_platform.statistics.entities import (
    MonitorStatistics,
)
from uptime_platform.statistics.protocols import (
    StatisticsRepositoryProtocol,
)
from uptime_platform.statistics.schemas import (
    StatisticsPeriod,
)

_PERIODS = {
    StatisticsPeriod.HOURS_24: timedelta(hours=24),
    StatisticsPeriod.DAYS_7: timedelta(days=7),
    StatisticsPeriod.DAYS_30: timedelta(days=30),
}


class StatisticsService:
    def __init__(
        self,
        repository: StatisticsRepositoryProtocol,
        monitor_repository: MonitorRepositoryProtocol,
        organization_id: UUID,
        retention_checks_days: int | None = None,
    ) -> None:
        self._repository = repository
        self._monitor_repository = monitor_repository
        self._organization_id = organization_id
        self._retention_checks_days = retention_checks_days

    async def get_monitor_statistics(
        self,
        monitor_id: UUID,
        period: StatisticsPeriod | None = None,
        starts_at: datetime | None = None,
        ends_at: datetime | None = None,
    ) -> MonitorStatistics | None:
        monitor = await self._monitor_repository.get_by_id(
            monitor_id,
            self._organization_id,
        )

        if monitor is None:
            return None

        now = datetime.now(UTC)
        if starts_at is not None and ends_at is not None:
            resolved_starts_at = starts_at.astimezone(UTC)
            resolved_ends_at = ends_at.astimezone(UTC)
        else:
            resolved_period = period or StatisticsPeriod.HOURS_24

            resolved_ends_at = now

            resolved_starts_at = resolved_ends_at - _PERIODS[resolved_period]

        statistics = await self._repository.get_monitor_statistics(
            monitor_id=monitor_id,
            starts_at=resolved_starts_at,
            ends_at=resolved_ends_at,
        )

        available_from = statistics.history_available_from
        is_partial = (
            statistics.total_checks == 0
            or available_from is None
            or resolved_starts_at < max(monitor.created_at, available_from)
            or resolved_ends_at > now
        )
        if self._retention_checks_days is not None:
            is_partial |= resolved_starts_at < now - timedelta(
                days=self._retention_checks_days
            )
        return replace(statistics, is_partial=is_partial)
