from datetime import datetime, timedelta

from sqlalchemy import Column, Table, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from uptime_platform.checks.models import CheckModel
from uptime_platform.core.config import Settings
from uptime_platform.incidents.entities import IncidentStatus
from uptime_platform.incidents.models import IncidentModel
from uptime_platform.notifications.models import NotificationDeliveryModel
from uptime_platform.outbox.models import OutboxEventModel


class RetentionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def cleanup(self, *, settings: Settings, now: datetime) -> dict[str, int]:
        checks = CheckModel.__table__
        incidents = IncidentModel.__table__
        deliveries = NotificationDeliveryModel.__table__
        events = OutboxEventModel.__table__
        notification_cutoff = now - timedelta(
            days=settings.retention_notifications_days
        )
        counts = {}
        counts["checks"] = await self._delete_batch(
            checks,
            checks.c.checked_at,
            now - timedelta(days=settings.retention_checks_days),
            settings.retention_batch_size,
        )
        counts["incidents"] = await self._delete_batch(
            incidents,
            incidents.c.resolved_at,
            now - timedelta(days=settings.retention_incidents_days),
            settings.retention_batch_size,
            incidents.c.status == IncidentStatus.RESOLVED,
        )
        counts["deliveries"] = await self._delete_batch(
            deliveries,
            deliveries.c.processed_at,
            notification_cutoff,
            settings.retention_batch_size,
            deliveries.c.lease_token.is_(None),
            deliveries.c.locked_until.is_(None),
            select(events.c.id)
            .where(
                events.c.id == deliveries.c.event_id,
                events.c.processed_at.is_not(None),
            )
            .exists(),
        )
        counts["events"] = await self._delete_batch(
            events,
            events.c.processed_at,
            notification_cutoff,
            settings.retention_batch_size,
            ~select(deliveries.c.id)
            .where(deliveries.c.event_id == events.c.id)
            .exists(),
        )
        return counts

    async def _delete_batch(
        self,
        table: Table,
        timestamp: Column,
        cutoff: datetime,
        limit: int,
        *conditions: ColumnElement[bool],
    ) -> int:
        candidates = (
            select(table.c.id)
            .where(timestamp < cutoff, *conditions)
            .order_by(timestamp)
            .limit(limit)
            .with_for_update(skip_locked=True)
            .cte("expired")
        )
        result = await self._session.execute(
            delete(table)
            .where(table.c.id.in_(select(candidates.c.id)))
            .returning(table.c.id)
        )
        return len(result.all())
