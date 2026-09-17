import asyncio
import logging
import time
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from uptime_platform.checks.entities import CheckResult
from uptime_platform.checks.factory import CheckerFactory
from uptime_platform.checks.protocols import CheckerFactoryProtocol
from uptime_platform.checks.service import CheckService
from uptime_platform.checks.sqlalchemy_repository import SqlAlchemyCheckRepository
from uptime_platform.core.metrics import Metrics, get_metrics
from uptime_platform.incidents.sqlalchemy_repository import SqlAlchemyIncidentRepository
from uptime_platform.maintenance.sqlalchemy_repository import (
    SqlAlchemyMaintenanceWindowRepository,
)
from uptime_platform.monitors.entities import MonitorClaim
from uptime_platform.monitors.sqlalchemy_repository import SqlAlchemyMonitorRepository
from uptime_platform.outbox.sqlalchemy_repository import SqlAlchemyOutboxRepository

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        poll_interval_seconds: int = 1,
        batch_size: int = 100,
        concurrency: int = 20,
        checker_factory: CheckerFactoryProtocol | None = None,
        lease_grace_seconds: float = 30,
        cleanup_timeout_seconds: float = 5,
        metrics: Metrics | None = None,
    ) -> None:
        if (
            poll_interval_seconds <= 0
            or batch_size < 1
            or concurrency < 1
            or lease_grace_seconds <= 0
            or cleanup_timeout_seconds <= 0
        ):
            raise ValueError("Scheduler limits and timeouts must be positive")
        self._metrics = metrics if metrics is not None else get_metrics("scheduler")
        self._session_factory = session_factory
        self._poll_interval_seconds = poll_interval_seconds
        self._batch_size = batch_size
        self._concurrency = concurrency
        self._lease_grace_seconds = lease_grace_seconds
        self._cleanup_timeout_seconds = cleanup_timeout_seconds
        self._run_lock = asyncio.Lock()
        self._checker_factory = (
            checker_factory if checker_factory is not None else CheckerFactory()
        )

    async def run_forever(self) -> None:
        while True:
            try:
                processed = await self.run_once()
                if processed:
                    logger.info("scheduler processed %d monitor(s)", processed)
            except Exception:
                logger.exception("scheduler iteration failed")
            await asyncio.sleep(self._poll_interval_seconds)

    async def run_once(self) -> int:
        async with self._run_lock:
            attempted: set[UUID] = set()
            successful = True
            while len(attempted) < self._batch_size:
                claims = await self._claim_monitors(
                    limit=min(self._concurrency, self._batch_size - len(attempted)),
                    exclude_ids=attempted,
                )
                if not claims:
                    break
                attempted.update(claim.monitor.id for claim in claims)
                try:
                    tasks = []
                    async with asyncio.TaskGroup() as group:
                        for claim in claims:
                            tasks.append(group.create_task(self._check_monitor(claim)))
                    successful = successful and all(
                        task.result() is not False for task in tasks
                    )
                finally:
                    released = await self._release_claims(claims)
                    successful = successful and released is not False
            if successful:
                self._metrics.scheduler_success.set_to_current_time()
            return len(attempted)

    async def _claim_monitors(
        self, *, limit: int, exclude_ids: set[UUID]
    ) -> list[MonitorClaim]:
        async with asyncio.timeout(self._lease_grace_seconds):
            async with self._session_factory() as session, session.begin():
                return await SqlAlchemyMonitorRepository(session).claim_due(
                    limit=limit,
                    lease_grace_seconds=self._lease_grace_seconds,
                    exclude_ids=exclude_ids,
                )

    async def _check_monitor(self, claim: MonitorClaim) -> bool:
        monitor = claim.monitor
        try:
            started_at = time.perf_counter()
            try:
                with self._metrics.check(monitor.monitor_type.value) as observation:
                    async with asyncio.timeout(monitor.timeout_seconds):
                        checker = self._checker_factory.create(monitor)
                        result = await checker.check(
                            timeout_seconds=monitor.timeout_seconds,
                        )
                        observation.success = result.success
            except TimeoutError:
                result = CheckResult(
                    success=False,
                    response_time_ms=(time.perf_counter() - started_at) * 1000,
                    status_code=None,
                    error="Check exceeded its total timeout",
                )

            async with asyncio.timeout(self._lease_grace_seconds):
                async with self._session_factory() as session, session.begin():
                    service = CheckService(
                        monitor_repository=SqlAlchemyMonitorRepository(session),
                        check_repository=SqlAlchemyCheckRepository(session),
                        incident_repository=SqlAlchemyIncidentRepository(session),
                        outbox_repository=SqlAlchemyOutboxRepository(session),
                        maintenance_repository=SqlAlchemyMaintenanceWindowRepository(
                            session
                        ),
                        checker_factory=self._checker_factory,
                        organization_id=monitor.organization_id,
                        metrics=self._metrics,
                    )
                    check = await service.record(
                        monitor_id=monitor.id,
                        result=result,
                        lease_token=claim.token,
                    )
                    if check is None:
                        logger.info(
                            "discarded stale check monitor_id=%s lease_token=%s",
                            monitor.id,
                            claim.token,
                        )
            return check is not None
        except Exception:
            logger.exception("monitor check failed monitor_id=%s", monitor.id)
            return False

    async def _release_claims(self, claims: list[MonitorClaim]) -> bool:
        try:
            async with asyncio.timeout(self._cleanup_timeout_seconds):
                async with self._session_factory() as session, session.begin():
                    repository = SqlAlchemyMonitorRepository(session)
                    for claim in claims:
                        await repository.release_check_lease(
                            claim.monitor.id, claim.token
                        )
            return True
        except Exception:
            logger.exception("failed to release monitor leases; awaiting expiry")
            return False
