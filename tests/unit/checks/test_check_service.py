from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from uptime_platform.checks.entities import CheckResult
from uptime_platform.checks.in_memory_repository import InMemoryCheckRepository
from uptime_platform.checks.service import CheckService
from uptime_platform.incidents.entities import Incident, IncidentStatus
from uptime_platform.incidents.in_memory_repository import (
    InMemoryIncidentRepository,
)
from uptime_platform.maintenance.entities import MaintenanceWindow
from uptime_platform.maintenance.in_memory_repository import (
    InMemoryMaintenanceWindowRepository,
)
from uptime_platform.monitors.entities import (
    HttpMonitorConfig,
    Monitor,
    MonitorStatus,
    MonitorType,
)
from uptime_platform.monitors.in_memory_repository import (
    InMemoryMonitorRepository,
)
from uptime_platform.organizations.constants import (
    DEFAULT_ORGANIZATION_ID,
)
from uptime_platform.outbox.entities import OutboxEventType
from uptime_platform.outbox.in_memory_repository import (
    InMemoryOutboxRepository,
)

pytestmark = pytest.mark.anyio


class StubChecker:
    def __init__(
        self,
        result: CheckResult,
    ) -> None:
        self._result = result
        self.calls = 0

    async def check(
        self,
        timeout_seconds: int,
    ) -> CheckResult:
        self.calls += 1

        return self._result


class StubCheckerFactory:
    def __init__(
        self,
        checker: StubChecker,
    ) -> None:
        self._checker = checker
        self.calls = 0

    def create(
        self,
        monitor: Monitor,
    ) -> StubChecker:
        self.calls += 1

        return self._checker


def make_monitor(
    status: MonitorStatus = MonitorStatus.PENDING,
    consecutive_failures: int = 0,
    consecutive_successes: int = 0,
    organization_id: UUID = DEFAULT_ORGANIZATION_ID,
) -> Monitor:
    now = datetime.now(UTC)

    return Monitor(
        id=uuid4(),
        organization_id=organization_id,
        name="Production API",
        monitor_type=MonitorType.HTTP,
        config=HttpMonitorConfig(
            url="https://example.com",
        ),
        interval_seconds=60,
        timeout_seconds=5,
        status=status,
        created_at=now,
        next_check_at=now,
        failure_threshold=3,
        recovery_threshold=2,
        consecutive_failures=consecutive_failures,
        consecutive_successes=consecutive_successes,
    )


def make_maintenance_window(
    monitor_id,
    *,
    starts_at: datetime,
    ends_at: datetime,
) -> MaintenanceWindow:
    return MaintenanceWindow(
        id=uuid4(),
        monitor_id=monitor_id,
        starts_at=starts_at,
        ends_at=ends_at,
        reason="Deployment",
        created_at=datetime.now(UTC),
    )


async def test_successful_check_changes_monitor_to_up() -> None:
    monitor_repository = InMemoryMonitorRepository()
    check_repository = InMemoryCheckRepository()
    incident_repository = InMemoryIncidentRepository()
    outbox_repository = InMemoryOutboxRepository()
    maintenance_repository = InMemoryMaintenanceWindowRepository()

    checker = StubChecker(
        CheckResult(
            success=True,
            response_time_ms=42.0,
            status_code=200,
            error=None,
        )
    )

    checker_factory = StubCheckerFactory(checker)

    monitor = make_monitor()

    await monitor_repository.create(monitor)

    service = CheckService(
        monitor_repository=monitor_repository,
        check_repository=check_repository,
        incident_repository=incident_repository,
        outbox_repository=outbox_repository,
        maintenance_repository=maintenance_repository,
        checker_factory=checker_factory,
        organization_id=DEFAULT_ORGANIZATION_ID,
    )

    check = await service.run(monitor.id)

    updated_monitor = await monitor_repository.get_by_id(
        monitor.id,
        DEFAULT_ORGANIZATION_ID,
    )

    assert check is not None
    assert check.monitor_id == monitor.id
    assert check.success is True
    assert check.response_time_ms == 42.0
    assert check.status_code == 200
    assert check.error is None

    assert updated_monitor is not None
    assert updated_monitor.status is MonitorStatus.UP

    assert checker.calls == 1


async def test_first_success_does_not_recover_down_monitor() -> None:
    monitor_repository = InMemoryMonitorRepository()
    check_repository = InMemoryCheckRepository()
    incident_repository = InMemoryIncidentRepository()
    outbox_repository = InMemoryOutboxRepository()
    maintenance_repository = InMemoryMaintenanceWindowRepository()

    checker = StubChecker(
        CheckResult(
            success=True,
            response_time_ms=50.0,
            status_code=200,
            error=None,
        )
    )
    checker_factory = StubCheckerFactory(checker)

    monitor = make_monitor(status=MonitorStatus.DOWN)

    await monitor_repository.create(monitor)

    service = CheckService(
        monitor_repository=monitor_repository,
        check_repository=check_repository,
        incident_repository=incident_repository,
        outbox_repository=outbox_repository,
        maintenance_repository=maintenance_repository,
        checker_factory=checker_factory,
        organization_id=DEFAULT_ORGANIZATION_ID,
    )

    await service.run(monitor.id)

    updated_monitor = await monitor_repository.get_by_id(
        monitor.id,
        DEFAULT_ORGANIZATION_ID,
    )

    assert updated_monitor is not None
    assert updated_monitor.status is MonitorStatus.DOWN
    assert updated_monitor.consecutive_successes == 1
    assert updated_monitor.consecutive_failures == 0


async def test_second_success_recovers_down_monitor() -> None:
    monitor_repository = InMemoryMonitorRepository()
    check_repository = InMemoryCheckRepository()
    incident_repository = InMemoryIncidentRepository()
    outbox_repository = InMemoryOutboxRepository()
    maintenance_repository = InMemoryMaintenanceWindowRepository()

    checker = StubChecker(
        CheckResult(
            success=True,
            response_time_ms=50.0,
            status_code=200,
            error=None,
        )
    )

    checker_factory = StubCheckerFactory(checker)

    monitor = make_monitor(
        status=MonitorStatus.DOWN,
        consecutive_successes=1,
    )

    await monitor_repository.create(monitor)

    service = CheckService(
        monitor_repository=monitor_repository,
        check_repository=check_repository,
        incident_repository=incident_repository,
        outbox_repository=outbox_repository,
        maintenance_repository=maintenance_repository,
        checker_factory=checker_factory,
        organization_id=DEFAULT_ORGANIZATION_ID,
    )

    await service.run(monitor.id)

    updated_monitor = await monitor_repository.get_by_id(
        monitor.id,
        DEFAULT_ORGANIZATION_ID,
    )

    assert updated_monitor is not None
    assert updated_monitor.status is MonitorStatus.UP
    assert updated_monitor.consecutive_successes == 2
    assert updated_monitor.consecutive_failures == 0


async def test_failed_check_keeps_down_monitor_down() -> None:
    monitor_repository = InMemoryMonitorRepository()
    check_repository = InMemoryCheckRepository()
    incident_repository = InMemoryIncidentRepository()
    outbox_repository = InMemoryOutboxRepository()
    maintenance_repository = InMemoryMaintenanceWindowRepository()

    checker = StubChecker(
        CheckResult(
            success=False,
            response_time_ms=1000.0,
            status_code=503,
            error=None,
        )
    )
    checker_factory = StubCheckerFactory(checker)

    monitor = make_monitor(status=MonitorStatus.DOWN)

    await monitor_repository.create(monitor)

    service = CheckService(
        monitor_repository=monitor_repository,
        check_repository=check_repository,
        incident_repository=incident_repository,
        outbox_repository=outbox_repository,
        maintenance_repository=maintenance_repository,
        checker_factory=checker_factory,
        organization_id=DEFAULT_ORGANIZATION_ID,
    )

    await service.run(monitor.id)

    updated_monitor = await monitor_repository.get_by_id(
        monitor.id,
        DEFAULT_ORGANIZATION_ID,
    )

    assert updated_monitor is not None
    assert updated_monitor.status is MonitorStatus.DOWN


async def test_paused_monitor_keeps_paused_status() -> None:
    monitor_repository = InMemoryMonitorRepository()
    check_repository = InMemoryCheckRepository()
    incident_repository = InMemoryIncidentRepository()
    outbox_repository = InMemoryOutboxRepository()
    maintenance_repository = InMemoryMaintenanceWindowRepository()

    checker = StubChecker(
        CheckResult(
            success=True,
            response_time_ms=30.0,
            status_code=200,
            error=None,
        )
    )

    checker_factory = StubCheckerFactory(checker)
    monitor = make_monitor(status=MonitorStatus.PAUSED)

    await monitor_repository.create(monitor)

    service = CheckService(
        monitor_repository=monitor_repository,
        check_repository=check_repository,
        incident_repository=incident_repository,
        outbox_repository=outbox_repository,
        maintenance_repository=maintenance_repository,
        checker_factory=checker_factory,
        organization_id=DEFAULT_ORGANIZATION_ID,
    )

    await service.run(monitor.id)

    updated_monitor = await monitor_repository.get_by_id(
        monitor.id,
        DEFAULT_ORGANIZATION_ID,
    )

    assert updated_monitor is not None
    assert updated_monitor.status is MonitorStatus.PAUSED


async def test_nonexistent_monitor_is_not_checked() -> None:
    monitor_repository = InMemoryMonitorRepository()
    check_repository = InMemoryCheckRepository()
    incident_repository = InMemoryIncidentRepository()
    outbox_repository = InMemoryOutboxRepository()
    maintenance_repository = InMemoryMaintenanceWindowRepository()

    checker = StubChecker(
        CheckResult(
            success=True,
            response_time_ms=42.0,
            status_code=200,
            error=None,
        )
    )

    checker_factory = StubCheckerFactory(checker)

    service = CheckService(
        monitor_repository=monitor_repository,
        check_repository=check_repository,
        incident_repository=incident_repository,
        outbox_repository=outbox_repository,
        maintenance_repository=maintenance_repository,
        checker_factory=checker_factory,
        organization_id=DEFAULT_ORGANIZATION_ID,
    )

    result = await service.run(uuid4())

    assert result is None
    assert checker.calls == 0


async def test_check_is_saved_to_history() -> None:
    monitor_repository = InMemoryMonitorRepository()
    check_repository = InMemoryCheckRepository()
    incident_repository = InMemoryIncidentRepository()
    outbox_repository = InMemoryOutboxRepository()
    maintenance_repository = InMemoryMaintenanceWindowRepository()

    checker = StubChecker(
        CheckResult(
            success=True,
            response_time_ms=42.0,
            status_code=200,
            error=None,
        )
    )

    checker_factory = StubCheckerFactory(checker)

    monitor = make_monitor()

    await monitor_repository.create(monitor)

    service = CheckService(
        monitor_repository=monitor_repository,
        check_repository=check_repository,
        incident_repository=incident_repository,
        outbox_repository=outbox_repository,
        maintenance_repository=maintenance_repository,
        checker_factory=checker_factory,
        organization_id=DEFAULT_ORGANIZATION_ID,
    )

    await service.run(monitor.id)

    history = await service.get_history(
        monitor_id=monitor.id,
        limit=50,
    )

    assert history is not None
    assert len(history) == 1

    check = history[0]

    assert check.monitor_id == monitor.id
    assert check.success is True
    assert check.status_code == 200


async def test_get_history_returns_none_for_nonexistent_monitor() -> None:
    monitor_repository = InMemoryMonitorRepository()
    check_repository = InMemoryCheckRepository()
    incident_repository = InMemoryIncidentRepository()
    outbox_repository = InMemoryOutboxRepository()
    maintenance_repository = InMemoryMaintenanceWindowRepository()

    checker = StubChecker(
        CheckResult(
            success=True,
            response_time_ms=42.0,
            status_code=200,
            error=None,
        )
    )

    checker_factory = StubCheckerFactory(checker)

    service = CheckService(
        monitor_repository=monitor_repository,
        check_repository=check_repository,
        incident_repository=incident_repository,
        outbox_repository=outbox_repository,
        maintenance_repository=maintenance_repository,
        checker_factory=checker_factory,
        organization_id=DEFAULT_ORGANIZATION_ID,
    )

    history = await service.get_history(
        monitor_id=uuid4(),
        limit=50,
    )

    assert history is None


async def test_third_failure_marks_monitor_down() -> None:
    monitor_repository = InMemoryMonitorRepository()
    check_repository = InMemoryCheckRepository()
    incident_repository = InMemoryIncidentRepository()
    outbox_repository = InMemoryOutboxRepository()
    maintenance_repository = InMemoryMaintenanceWindowRepository()

    checker = StubChecker(
        CheckResult(
            success=False,
            response_time_ms=2000.0,
            status_code=None,
            error="Connection failed",
        )
    )

    checker_factory = StubCheckerFactory(checker)

    monitor = make_monitor(
        status=MonitorStatus.UP,
        consecutive_failures=2,
    )

    await monitor_repository.create(monitor)

    service = CheckService(
        monitor_repository=monitor_repository,
        check_repository=check_repository,
        incident_repository=incident_repository,
        outbox_repository=outbox_repository,
        maintenance_repository=maintenance_repository,
        checker_factory=checker_factory,
        organization_id=DEFAULT_ORGANIZATION_ID,
    )

    await service.run(monitor.id)

    updated_monitor = await monitor_repository.get_by_id(
        monitor.id,
        DEFAULT_ORGANIZATION_ID,
    )

    assert updated_monitor is not None
    assert updated_monitor.status is MonitorStatus.DOWN
    assert updated_monitor.consecutive_failures == 3
    assert updated_monitor.consecutive_successes == 0


async def test_monitor_down_transition_creates_incident() -> None:
    monitor_repository = InMemoryMonitorRepository()
    check_repository = InMemoryCheckRepository()
    incident_repository = InMemoryIncidentRepository()
    outbox_repository = InMemoryOutboxRepository()
    maintenance_repository = InMemoryMaintenanceWindowRepository()

    checker = StubChecker(
        CheckResult(
            success=False,
            response_time_ms=2000.0,
            status_code=None,
            error="Connection failed",
        )
    )

    checker_factory = StubCheckerFactory(checker)

    monitor = make_monitor(
        status=MonitorStatus.UP,
        consecutive_failures=2,
    )

    await monitor_repository.create(monitor)

    service = CheckService(
        monitor_repository=monitor_repository,
        check_repository=check_repository,
        incident_repository=incident_repository,
        outbox_repository=outbox_repository,
        maintenance_repository=maintenance_repository,
        checker_factory=checker_factory,
        organization_id=DEFAULT_ORGANIZATION_ID,
    )

    await service.run(monitor.id)

    incident = await incident_repository.get_open_by_monitor_id(monitor.id)

    assert incident is not None
    assert incident.monitor_id == monitor.id
    assert incident.status is IncidentStatus.OPEN
    assert incident.resolved_at is None

    events = await outbox_repository.claim_pending(
        limit=10,
    )

    assert len(events) == 1

    event = events[0]

    assert event.organization_id == monitor.organization_id

    assert event.event_type is OutboxEventType.INCIDENT_OPENED

    assert event.payload["incident_id"] == str(incident.id)

    assert event.payload["monitor_id"] == str(monitor.id)

    assert event.processed_at is None


async def test_monitor_recovery_resolves_incident() -> None:
    monitor_repository = InMemoryMonitorRepository()
    check_repository = InMemoryCheckRepository()
    incident_repository = InMemoryIncidentRepository()
    outbox_repository = InMemoryOutboxRepository()
    maintenance_repository = InMemoryMaintenanceWindowRepository()

    checker = StubChecker(
        CheckResult(
            success=True,
            response_time_ms=50.0,
            status_code=200,
            error=None,
        )
    )

    checker_factory = StubCheckerFactory(checker)

    monitor = make_monitor(
        status=MonitorStatus.DOWN,
        consecutive_successes=1,
    )

    await monitor_repository.create(monitor)

    incident = Incident(
        id=uuid4(),
        monitor_id=monitor.id,
        status=IncidentStatus.OPEN,
        started_at=datetime.now(UTC),
        resolved_at=None,
    )

    await incident_repository.create(incident)

    service = CheckService(
        monitor_repository=monitor_repository,
        check_repository=check_repository,
        incident_repository=incident_repository,
        outbox_repository=outbox_repository,
        maintenance_repository=maintenance_repository,
        checker_factory=checker_factory,
        organization_id=DEFAULT_ORGANIZATION_ID,
    )

    await service.run(monitor.id)

    incidents = await incident_repository.get_by_monitor_id(
        monitor.id,
        limit=10,
    )

    assert len(incidents) == 1

    resolved_incident = incidents[0]

    assert resolved_incident.status is IncidentStatus.RESOLVED
    assert resolved_incident.resolved_at is not None

    events = await outbox_repository.claim_pending(
        limit=10,
    )

    assert len(events) == 1

    event = events[0]

    assert event.organization_id == monitor.organization_id

    assert event.event_type is OutboxEventType.INCIDENT_RESOLVED

    assert event.payload["incident_id"] == str(resolved_incident.id)

    assert event.payload["monitor_id"] == str(monitor.id)


async def test_failed_check_during_maintenance_does_not_change_monitor_state() -> None:
    monitor_repository = InMemoryMonitorRepository()
    check_repository = InMemoryCheckRepository()
    incident_repository = InMemoryIncidentRepository()
    outbox_repository = InMemoryOutboxRepository()
    maintenance_repository = InMemoryMaintenanceWindowRepository()

    checker = StubChecker(
        CheckResult(
            success=False,
            response_time_ms=2000.0,
            status_code=503,
            error=None,
        )
    )

    checker_factory = StubCheckerFactory(checker)

    monitor = make_monitor(
        status=MonitorStatus.UP,
        consecutive_failures=2,
    )

    await monitor_repository.create(monitor)

    now = datetime.now(UTC)

    maintenance = make_maintenance_window(
        monitor.id,
        starts_at=now - timedelta(minutes=5),
        ends_at=now + timedelta(minutes=5),
    )

    await maintenance_repository.create(maintenance)

    service = CheckService(
        monitor_repository=monitor_repository,
        check_repository=check_repository,
        incident_repository=incident_repository,
        outbox_repository=outbox_repository,
        maintenance_repository=maintenance_repository,
        checker_factory=checker_factory,
        organization_id=DEFAULT_ORGANIZATION_ID,
    )

    check = await service.run(monitor.id)

    updated_monitor = await monitor_repository.get_by_id(
        monitor.id,
        DEFAULT_ORGANIZATION_ID,
    )

    assert check is not None
    assert check.success is False

    assert updated_monitor is not None
    assert updated_monitor.status is MonitorStatus.UP

    assert updated_monitor.consecutive_failures == monitor.consecutive_failures
    assert updated_monitor.consecutive_successes == monitor.consecutive_successes

    assert updated_monitor.next_check_at > monitor.next_check_at

    history = await service.get_history(
        monitor_id=monitor.id,
        limit=50,
    )

    assert history is not None
    assert len(history) == 1
    assert history[0].success is False

    incident = await incident_repository.get_open_by_monitor_id(monitor.id)

    assert incident is None

    events = await outbox_repository.claim_pending(
        limit=10,
    )

    assert events == []


async def test_successful_check_during_maintenance_does_not_resolve_incident() -> None:
    monitor_repository = InMemoryMonitorRepository()
    check_repository = InMemoryCheckRepository()
    incident_repository = InMemoryIncidentRepository()
    outbox_repository = InMemoryOutboxRepository()
    maintenance_repository = InMemoryMaintenanceWindowRepository()

    checker = StubChecker(
        CheckResult(
            success=True,
            response_time_ms=50.0,
            status_code=200,
            error=None,
        )
    )

    checker_factory = StubCheckerFactory(checker)

    monitor = make_monitor(
        status=MonitorStatus.DOWN,
        consecutive_successes=1,
    )

    await monitor_repository.create(monitor)

    incident = Incident(
        id=uuid4(),
        monitor_id=monitor.id,
        status=IncidentStatus.OPEN,
        started_at=datetime.now(UTC),
        resolved_at=None,
    )

    await incident_repository.create(incident)

    now = datetime.now(UTC)

    maintenance = make_maintenance_window(
        monitor.id,
        starts_at=now - timedelta(minutes=5),
        ends_at=now + timedelta(minutes=5),
    )

    await maintenance_repository.create(maintenance)

    service = CheckService(
        monitor_repository=monitor_repository,
        check_repository=check_repository,
        incident_repository=incident_repository,
        outbox_repository=outbox_repository,
        maintenance_repository=maintenance_repository,
        checker_factory=checker_factory,
        organization_id=DEFAULT_ORGANIZATION_ID,
    )

    check = await service.run(monitor.id)

    updated_monitor = await monitor_repository.get_by_id(
        monitor.id,
        DEFAULT_ORGANIZATION_ID,
    )

    assert check is not None
    assert check.success is True

    assert updated_monitor is not None
    assert updated_monitor.status is MonitorStatus.DOWN

    assert updated_monitor.consecutive_successes == 1
    assert updated_monitor.consecutive_failures == 0

    open_incident = await incident_repository.get_open_by_monitor_id(monitor.id)

    assert open_incident is not None
    assert open_incident.id == incident.id
    assert open_incident.status is IncidentStatus.OPEN
    assert open_incident.resolved_at is None

    events = await outbox_repository.claim_pending(
        limit=10,
    )

    assert events == []


async def test_expired_maintenance_does_not_suppress_monitor_transition() -> None:
    monitor_repository = InMemoryMonitorRepository()
    check_repository = InMemoryCheckRepository()
    incident_repository = InMemoryIncidentRepository()
    outbox_repository = InMemoryOutboxRepository()
    maintenance_repository = InMemoryMaintenanceWindowRepository()

    checker = StubChecker(
        CheckResult(
            success=False,
            response_time_ms=2000.0,
            status_code=503,
            error=None,
        )
    )

    checker_factory = StubCheckerFactory(checker)

    monitor = make_monitor(
        status=MonitorStatus.UP,
        consecutive_failures=2,
    )

    await monitor_repository.create(monitor)

    now = datetime.now(UTC)

    maintenance = make_maintenance_window(
        monitor.id,
        starts_at=now - timedelta(hours=2),
        ends_at=now - timedelta(hours=1),
    )

    await maintenance_repository.create(maintenance)

    service = CheckService(
        monitor_repository=monitor_repository,
        check_repository=check_repository,
        incident_repository=incident_repository,
        outbox_repository=outbox_repository,
        maintenance_repository=maintenance_repository,
        checker_factory=checker_factory,
        organization_id=DEFAULT_ORGANIZATION_ID,
    )

    await service.run(monitor.id)

    updated_monitor = await monitor_repository.get_by_id(
        monitor.id,
        DEFAULT_ORGANIZATION_ID,
    )

    assert updated_monitor is not None
    assert updated_monitor.status is MonitorStatus.DOWN
    assert updated_monitor.consecutive_failures == 3

    incident = await incident_repository.get_open_by_monitor_id(monitor.id)

    assert incident is not None
    assert incident.status is IncidentStatus.OPEN

    events = await outbox_repository.claim_pending(
        limit=10,
    )

    assert len(events) == 1
    assert events[0].event_type is OutboxEventType.INCIDENT_OPENED


@pytest.mark.parametrize("success", [True, False])
async def test_manual_check_metrics_count_execution_once(success):
    from uptime_platform.core.metrics import Metrics

    metrics = Metrics("api")
    monitors = InMemoryMonitorRepository()
    monitor = make_monitor()
    await monitors.create(monitor)
    service = CheckService(
        monitor_repository=monitors,
        check_repository=InMemoryCheckRepository(),
        incident_repository=InMemoryIncidentRepository(),
        outbox_repository=InMemoryOutboxRepository(),
        maintenance_repository=InMemoryMaintenanceWindowRepository(),
        checker_factory=StubCheckerFactory(
            StubChecker(CheckResult(success, 2, 200, None))
        ),
        organization_id=DEFAULT_ORGANIZATION_ID,
        metrics=metrics,
    )
    assert await service.run(uuid4()) is None
    await service.run(monitor.id)
    labels = {"monitor_type": "http", "outcome": "success" if success else "failure"}
    assert metrics.registry.get_sample_value("uptime_checks_total", labels) == 1
    assert (
        metrics.registry.get_sample_value(
            "uptime_check_duration_seconds_count", {"monitor_type": "http"}
        )
        == 1
    )
