from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)

from uptime_platform.statistics.dependencies import (
    get_statistics_service,
)
from uptime_platform.statistics.schemas import (
    MonitorStatisticsResponse,
    StatisticsPeriod,
    StatisticsQuery,
)
from uptime_platform.statistics.service import (
    StatisticsService,
)

router = APIRouter(
    prefix="/api/v1/monitors",
    tags=["statistics"],
)


@router.get(
    "/{monitor_id}/statistics",
    response_model=MonitorStatisticsResponse,
)
async def get_monitor_statistics(
    monitor_id: UUID,
    service: Annotated[
        StatisticsService,
        Depends(get_statistics_service),
    ],
    query: Annotated[
        StatisticsQuery,
        Query(),
    ],
) -> MonitorStatisticsResponse:
    statistics = await service.get_monitor_statistics(
        monitor_id=monitor_id,
        period=query.period,
        starts_at=query.starts_at,
        ends_at=query.ends_at,
    )

    if statistics is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Monitor not found",
        )

    effective_period = query.period

    if effective_period is None and query.starts_at is None:
        effective_period = StatisticsPeriod.HOURS_24

    return MonitorStatisticsResponse(
        monitor_id=statistics.monitor_id,
        period=effective_period,
        starts_at=statistics.starts_at,
        ends_at=statistics.ends_at,
        total_checks=statistics.total_checks,
        successful_checks=(statistics.successful_checks),
        failed_checks=statistics.failed_checks,
        uptime_percentage=(statistics.uptime_percentage),
        average_response_time_ms=(statistics.average_response_time_ms),
        history_available_from=statistics.history_available_from,
        first_check_at=statistics.first_check_at,
        last_check_at=statistics.last_check_at,
        is_partial=statistics.is_partial,
    )
