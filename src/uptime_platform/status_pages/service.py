from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from uptime_platform.monitors.entities import (
    Monitor,
    MonitorStatus,
)
from uptime_platform.monitors.protocols import (
    MonitorRepositoryProtocol,
)
from uptime_platform.status_pages.entities import (
    StatusPage,
    StatusPageMonitor,
    StatusPageStatus,
)
from uptime_platform.status_pages.protocols import (
    StatusPageRepositoryProtocol,
)
from uptime_platform.status_pages.schemas import (
    PublicStatusPageResponse,
    StatusPageCreate,
    StatusPageMonitorResponse,
    StatusPageUpdate,
)


def calculate_status_page_status(
    monitors: list[Monitor],
) -> StatusPageStatus:
    active_monitors = [
        monitor for monitor in monitors if monitor.status is not MonitorStatus.PAUSED
    ]

    if not active_monitors:
        return StatusPageStatus.UNKNOWN

    down_count = sum(
        monitor.status is MonitorStatus.DOWN for monitor in active_monitors
    )

    if down_count == 0:
        if any(monitor.status is MonitorStatus.PENDING for monitor in active_monitors):
            return StatusPageStatus.UNKNOWN
        return StatusPageStatus.OPERATIONAL

    if down_count == len(active_monitors):
        return StatusPageStatus.MAJOR_OUTAGE

    return StatusPageStatus.PARTIAL_OUTAGE


class StatusPageService:
    def __init__(
        self,
        repository: StatusPageRepositoryProtocol,
        monitor_repository: MonitorRepositoryProtocol,
        organization_id: UUID,
    ) -> None:
        self._repository = repository
        self._monitor_repository = monitor_repository
        self._organization_id = organization_id

    async def create(
        self,
        data: StatusPageCreate,
    ) -> StatusPage | None:
        existing = await self._repository.get_by_slug(data.slug)

        if existing is not None:
            return None

        page = StatusPage(
            id=uuid4(),
            organization_id=self._organization_id,
            name=data.name,
            slug=data.slug,
            published=data.published,
            created_at=datetime.now(UTC),
        )

        return await self._repository.create(page)

    async def get_all(
        self,
    ) -> list[StatusPage]:
        return await self._repository.get_all(self._organization_id)

    async def get(
        self,
        page_id: UUID,
    ) -> StatusPage | None:
        return await self._repository.get_by_id(
            page_id,
            self._organization_id,
        )

    async def update(
        self,
        page_id: UUID,
        data: StatusPageUpdate,
    ) -> StatusPage | None:
        page = await self._repository.get_by_id(
            page_id,
            self._organization_id,
        )

        if page is None:
            return None

        changes = data.model_dump(exclude_unset=True)

        updated_page = replace(
            page,
            **changes,
        )

        return await self._repository.update(updated_page)

    async def delete(
        self,
        page_id: UUID,
    ) -> bool:
        return await self._repository.delete(
            page_id,
            self._organization_id,
        )

    async def add_monitor(
        self,
        page_id: UUID,
        monitor_id: UUID,
    ) -> bool | None:
        page = await self._repository.get_by_id(
            page_id,
            self._organization_id,
        )

        if page is None:
            return None

        monitor = await self._monitor_repository.get_by_id(
            monitor_id,
            self._organization_id,
        )

        if monitor is None:
            return None

        if monitor.organization_id != page.organization_id:
            return None

        existing = await self._repository.get_monitors(page_id)

        relation = StatusPageMonitor(
            status_page_id=page_id,
            monitor_id=monitor_id,
            position=len(existing),
        )

        return await self._repository.add_monitor(relation)

    async def remove_monitor(
        self,
        page_id: UUID,
        monitor_id: UUID,
    ) -> bool:
        page = await self._repository.get_by_id(
            page_id,
            self._organization_id,
        )

        if page is None:
            return False

        return await self._repository.remove_monitor(
            page_id,
            monitor_id,
        )

    async def get_monitors(
        self,
        page_id: UUID,
    ) -> list[StatusPageMonitorResponse] | None:
        page = await self._repository.get_by_id(
            page_id,
            self._organization_id,
        )

        if page is None:
            return None

        relations = await self._repository.get_monitors(page_id)

        monitors: list[StatusPageMonitorResponse] = []

        for relation in relations:
            monitor = await self._monitor_repository.get_by_id(
                relation.monitor_id,
                self._organization_id,
            )

            if monitor is None:
                continue

            monitors.append(
                StatusPageMonitorResponse(
                    id=monitor.id,
                    name=monitor.name,
                    status=monitor.status,
                )
            )

        return monitors


class PublicStatusPageService:
    def __init__(
        self,
        repository: StatusPageRepositoryProtocol,
        monitor_repository: MonitorRepositoryProtocol,
    ) -> None:
        self._repository = repository
        self._monitor_repository = monitor_repository

    async def get(
        self,
        slug: str,
    ) -> PublicStatusPageResponse | None:
        page = await self._repository.get_by_slug(slug)

        if page is None or not page.published:
            return None

        relations = await self._repository.get_monitors(page.id)

        monitors: list[Monitor] = []

        for relation in relations:
            monitor = await self._monitor_repository.get_by_id(
                relation.monitor_id,
                page.organization_id,
            )

            if monitor is not None:
                monitors.append(monitor)

        return PublicStatusPageResponse(
            name=page.name,
            slug=page.slug,
            status=calculate_status_page_status(monitors),
            monitors=[
                StatusPageMonitorResponse(
                    id=monitor.id,
                    name=monitor.name,
                    status=monitor.status,
                )
                for monitor in monitors
            ],
        )
