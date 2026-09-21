from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from uptime_platform.checks.entities import (
    Check,
    CheckResult,
)
from uptime_platform.checks.protocols import (
    CheckerFactoryProtocol,
    CheckRepositoryProtocol,
)
from uptime_platform.core.metrics import Metrics, get_metrics
from uptime_platform.incidents.entities import (
    Incident,
    IncidentStatus,
)
from uptime_platform.incidents.protocols import (
    IncidentRepositoryProtocol,
)
from uptime_platform.maintenance.protocols import (
    MaintenanceWindowRepositoryProtocol,
)
from uptime_platform.monitors.entities import Monitor, MonitorStatus
from uptime_platform.monitors.protocols import (
    MonitorRepositoryProtocol,
)
from uptime_platform.monitors.state import (
    apply_check_result,
)
from uptime_platform.notifications.content import incident_payload
from uptime_platform.outbox.entities import (
    OutboxEvent,
    OutboxEventType,
)
from uptime_platform.outbox.protocols import (
    OutboxRepositoryProtocol,
)


class CheckService:
    def __init__(
        self,
        monitor_repository: MonitorRepositoryProtocol,
        check_repository: CheckRepositoryProtocol,
        incident_repository: IncidentRepositoryProtocol,
        outbox_repository: OutboxRepositoryProtocol,
        checker_factory: CheckerFactoryProtocol,
        maintenance_repository: MaintenanceWindowRepositoryProtocol,
        organization_id: UUID,
        metrics: Metrics | None = None,
    ) -> None:
        self._monitor_repository = monitor_repository
        self._check_repository = check_repository
        self._incident_repository = incident_repository
        self._outbox_repository = outbox_repository
        self._checker_factory = checker_factory
        self._maintenance_repository = maintenance_repository
        self._organization_id = organization_id
        self._metrics = metrics if metrics is not None else get_metrics("api")

    async def run(
        self,
        monitor_id: UUID,
    ) -> Check | None:
        monitor = await self._monitor_repository.get_by_id(
            monitor_id,
            self._organization_id,
        )

        if monitor is None:
            return None

        with self._metrics.check(monitor.monitor_type.value) as observation:
            checker = self._checker_factory.create(monitor)
            result = await checker.check(
                timeout_seconds=monitor.timeout_seconds,
            )
            observation.success = result.success

        return await self.record(
            monitor_id=monitor.id,
            result=result,
            checked_monitor=monitor,
        )

    async def get_history(
        self,
        monitor_id: UUID,
        limit: int,
    ) -> list[Check] | None:
        monitor = await self._monitor_repository.get_by_id(
            monitor_id,
            self._organization_id,
        )

        if monitor is None:
            return None

        return await self._check_repository.get_by_monitor_id(
            monitor_id=monitor_id,
            limit=limit,
        )

    async def record(
        self,
        monitor_id: UUID,
        result: CheckResult,
        *,
        lease_token: UUID | None = None,
        checked_monitor: Monitor | None = None,
    ) -> Check | None:
        if lease_token is None:
            monitor = await self._monitor_repository.get_by_id_for_update(monitor_id)
        else:
            monitor = await self._monitor_repository.get_by_id_for_update(
                monitor_id, lease_token=lease_token
            )

        if monitor is None:
            return None

        check = await self._check_repository.create(
            monitor_id=monitor.id,
            result=result,
        )

        maintenance = await self._maintenance_repository.get_active(
            monitor_id=monitor.id,
            now=check.checked_at,
        )

        if maintenance is not None:
            updated_monitor = replace(
                monitor,
                next_check_at=(
                    check.checked_at + timedelta(seconds=monitor.interval_seconds)
                ),
            )

            await self._monitor_repository.update(updated_monitor)

            if lease_token is not None:
                await self._monitor_repository.release_check_lease(
                    monitor_id, lease_token
                )
            return check

        updated_monitor = apply_check_result(
            monitor=monitor,
            success=result.success,
        )

        updated_monitor = replace(
            updated_monitor,
            next_check_at=(
                check.checked_at + timedelta(seconds=monitor.interval_seconds)
            ),
        )

        await self._monitor_repository.update(updated_monitor)

        await self._handle_incident_transition(
            previous_status=monitor.status,
            current_status=updated_monitor.status,
            monitor_id=monitor.id,
            organization_id=monitor.organization_id,
            checked_at=check.checked_at,
            monitor=checked_monitor or monitor,
            result=result,
        )

        if lease_token is not None:
            await self._monitor_repository.release_check_lease(monitor_id, lease_token)
        return check

    async def _handle_incident_transition(
        self,
        previous_status: MonitorStatus,
        current_status: MonitorStatus,
        monitor_id: UUID,
        organization_id: UUID,
        checked_at: datetime,
        monitor: Monitor,
        result: CheckResult,
    ) -> None:
        if (
            previous_status is not MonitorStatus.DOWN
            and current_status is MonitorStatus.DOWN
        ):
            incident = Incident(
                id=uuid4(),
                monitor_id=monitor_id,
                status=IncidentStatus.OPEN,
                started_at=checked_at,
                resolved_at=None,
            )

            await self._incident_repository.create(incident)

            event = OutboxEvent(
                id=uuid4(),
                organization_id=organization_id,
                event_type=OutboxEventType.INCIDENT_OPENED,
                payload=incident_payload(monitor, incident, result),
                created_at=checked_at,
                processed_at=None,
            )

            await self._outbox_repository.create(event)

            return

        if previous_status is MonitorStatus.DOWN and current_status is MonitorStatus.UP:
            incident = await self._incident_repository.get_open_by_monitor_id(
                monitor_id
            )

            if incident is None:
                return

            resolved_incident = replace(
                incident,
                status=IncidentStatus.RESOLVED,
                resolved_at=checked_at,
            )

            event = OutboxEvent(
                id=uuid4(),
                organization_id=organization_id,
                event_type=OutboxEventType.INCIDENT_RESOLVED,
                payload=incident_payload(monitor, resolved_incident, result),
                created_at=checked_at,
                processed_at=None,
            )

            await self._outbox_repository.create(event)

            await self._incident_repository.update(resolved_incident)
