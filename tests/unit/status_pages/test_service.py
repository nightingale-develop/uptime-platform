from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from uptime_platform.monitors.entities import (
    HttpMonitorConfig,
    Monitor,
    MonitorStatus,
    MonitorType,
)
from uptime_platform.organizations.constants import (
    DEFAULT_ORGANIZATION_ID,
)
from uptime_platform.status_pages.entities import (
    StatusPageStatus,
)
from uptime_platform.status_pages.service import (
    calculate_status_page_status,
)


def make_monitor(
    status: MonitorStatus,
    organization_id: UUID = DEFAULT_ORGANIZATION_ID,
) -> Monitor:
    now = datetime.now(UTC)

    return Monitor(
        id=uuid4(),
        organization_id=organization_id,
        name="API",
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
        consecutive_failures=0,
        consecutive_successes=0,
    )


def test_empty_status_page_is_unknown() -> None:
    status = calculate_status_page_status([])

    assert status is StatusPageStatus.UNKNOWN


def test_all_monitors_up_is_operational() -> None:
    monitors = [
        make_monitor(MonitorStatus.UP),
        make_monitor(MonitorStatus.UP),
    ]

    status = calculate_status_page_status(monitors)

    assert status is StatusPageStatus.OPERATIONAL


def test_one_down_monitor_is_partial_outage() -> None:
    monitors = [
        make_monitor(MonitorStatus.UP),
        make_monitor(MonitorStatus.DOWN),
    ]

    status = calculate_status_page_status(monitors)

    assert status is StatusPageStatus.PARTIAL_OUTAGE


def test_all_monitors_down_is_major_outage() -> None:
    monitors = [
        make_monitor(MonitorStatus.DOWN),
        make_monitor(MonitorStatus.DOWN),
    ]

    status = calculate_status_page_status(monitors)

    assert status is StatusPageStatus.MAJOR_OUTAGE


def test_paused_monitors_are_ignored() -> None:
    monitors = [
        make_monitor(MonitorStatus.UP),
        make_monitor(MonitorStatus.PAUSED),
    ]

    status = calculate_status_page_status(monitors)

    assert status is StatusPageStatus.OPERATIONAL


def test_only_paused_monitors_is_unknown() -> None:
    monitors = [
        make_monitor(MonitorStatus.PAUSED),
        make_monitor(MonitorStatus.PAUSED),
    ]

    status = calculate_status_page_status(monitors)

    assert status is StatusPageStatus.UNKNOWN


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ([MonitorStatus.PENDING], StatusPageStatus.UNKNOWN),
        ([MonitorStatus.PENDING, MonitorStatus.PENDING], StatusPageStatus.UNKNOWN),
        ([MonitorStatus.PENDING, MonitorStatus.PAUSED], StatusPageStatus.UNKNOWN),
        ([MonitorStatus.UP, MonitorStatus.PENDING], StatusPageStatus.UNKNOWN),
        ([MonitorStatus.DOWN, MonitorStatus.PENDING], StatusPageStatus.PARTIAL_OUTAGE),
        (
            [MonitorStatus.UP, MonitorStatus.DOWN, MonitorStatus.PENDING],
            StatusPageStatus.PARTIAL_OUTAGE,
        ),
    ],
)
def test_pending_monitors_do_not_imply_health_or_hide_outages(
    statuses: list[MonitorStatus],
    expected: StatusPageStatus,
) -> None:
    assert (
        calculate_status_page_status([make_monitor(status) for status in statuses])
        is expected
    )
