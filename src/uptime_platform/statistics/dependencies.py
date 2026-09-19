from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from uptime_platform.auth.dependencies import (
    get_organization_context,
)
from uptime_platform.auth.entities import (
    OrganizationContext,
)
from uptime_platform.core.config import Settings, get_settings
from uptime_platform.db.session import get_db_session
from uptime_platform.monitors.sqlalchemy_repository import (
    SqlAlchemyMonitorRepository,
)
from uptime_platform.statistics.service import (
    StatisticsService,
)
from uptime_platform.statistics.sqlalchemy_repository import (
    SqlAlchemyStatisticsRepository,
)


def get_statistics_service(
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
    context: Annotated[
        OrganizationContext,
        Depends(get_organization_context),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StatisticsService:
    return StatisticsService(
        repository=SqlAlchemyStatisticsRepository(session),
        monitor_repository=SqlAlchemyMonitorRepository(session),
        organization_id=context.organization.id,
        retention_checks_days=(
            settings.retention_checks_days if settings.retention_enabled else None
        ),
    )
