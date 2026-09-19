from datetime import datetime
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from uptime_platform.checks.models import CheckModel
from uptime_platform.statistics.entities import (
    MonitorStatistics,
)


class SqlAlchemyStatisticsRepository:
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def get_monitor_statistics(
        self,
        monitor_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
    ) -> MonitorStatistics:
        oldest_check = (
            select(CheckModel.checked_at)
            .where(CheckModel.monitor_id == monitor_id)
            .order_by(CheckModel.checked_at)
            .limit(1)
            .correlate(None)
            .scalar_subquery()
        )
        statement = select(
            func.count(CheckModel.id),
            func.sum(
                case(
                    (
                        CheckModel.success.is_(True),
                        1,
                    ),
                    else_=0,
                )
            ),
            func.avg(
                case(
                    (
                        CheckModel.success.is_(True),
                        CheckModel.response_time_ms,
                    ),
                    else_=None,
                )
            ),
            oldest_check,
            func.min(CheckModel.checked_at),
            func.max(CheckModel.checked_at),
        ).where(
            CheckModel.monitor_id == monitor_id,
            CheckModel.checked_at >= starts_at,
            CheckModel.checked_at < ends_at,
        )

        result = await self._session.execute(statement)

        row = result.one()

        total_checks = row[0] or 0
        successful_checks = row[1] or 0

        failed_checks = total_checks - successful_checks

        uptime_percentage: float | None = None

        if total_checks > 0:
            uptime_percentage = round(
                successful_checks / total_checks * 100,
                2,
            )

        average_response_time_ms = (
            round(float(row[2]), 2) if row[2] is not None else None
        )

        return MonitorStatistics(
            monitor_id=monitor_id,
            starts_at=starts_at,
            ends_at=ends_at,
            total_checks=total_checks,
            successful_checks=successful_checks,
            failed_checks=failed_checks,
            uptime_percentage=uptime_percentage,
            average_response_time_ms=(average_response_time_ms),
            history_available_from=row[3],
            first_check_at=row[4],
            last_check_at=row[5],
        )
