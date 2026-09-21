import asyncio
import logging
from uuid import UUID

import httpx2
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)

from uptime_platform.core.metrics import Metrics, get_metrics
from uptime_platform.notifications.entities import (
    NotificationDelivery,
)
from uptime_platform.notifications.factory import (
    create_notification_channel,
)
from uptime_platform.notifications.service import (
    NotificationFanoutService,
    NotificationService,
)
from uptime_platform.notifications.sqlalchemy_repository import (
    SqlAlchemyNotificationDeliveryRepository,
    SqlAlchemyNotificationDestinationRepository,
)
from uptime_platform.outbox.sqlalchemy_repository import (
    SqlAlchemyOutboxRepository,
)

logger = logging.getLogger(__name__)


class NotificationWorker:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        http_client: httpx2.AsyncClient,
        poll_interval_seconds: int = 5,
        batch_size: int = 100,
        concurrency: int = 10,
        max_attempts: int = 5,
        lease_seconds: int = 60,
        notification_timeout_seconds: float = 5,
        database_timeout_seconds: float = 5,
        cleanup_timeout_seconds: float = 5,
        metrics: Metrics | None = None,
        public_app_url: str = "",
    ) -> None:
        if (
            min(
                poll_interval_seconds,
                batch_size,
                concurrency,
                max_attempts,
                lease_seconds,
                notification_timeout_seconds,
                database_timeout_seconds,
                cleanup_timeout_seconds,
            )
            <= 0
        ):
            raise ValueError("Worker limits and timeouts must be positive")
        self._metrics = metrics if metrics is not None else get_metrics("worker")
        self._concurrency = concurrency
        self._database_timeout_seconds = database_timeout_seconds
        self._cleanup_timeout_seconds = cleanup_timeout_seconds
        self._run_lock = asyncio.Lock()
        self._session_factory = session_factory
        self._http_client = http_client

        self._poll_interval_seconds = poll_interval_seconds
        self._batch_size = batch_size
        self._max_attempts = max_attempts
        self._lease_seconds = max(
            lease_seconds,
            notification_timeout_seconds + 3 * database_timeout_seconds + 1,
        )
        self._notification_timeout_seconds = notification_timeout_seconds
        self._public_app_url = public_app_url

        self._notification_service = NotificationService(metrics=self._metrics)

    async def run_forever(self) -> None:
        while True:
            try:
                fanout_count, delivery_count = await self.run_once()

                if fanout_count > 0 or delivery_count > 0:
                    logger.info(
                        "notification worker fanout=%d deliveries=%d",
                        fanout_count,
                        delivery_count,
                    )

            except Exception:
                logger.exception("notification worker iteration failed")

            await asyncio.sleep(self._poll_interval_seconds)

    async def run_once(self) -> tuple[int, int]:
        async with self._run_lock:
            async with asyncio.timeout(self._database_timeout_seconds):
                fanout_count = await self._fan_out_pending_events()
            attempted: set[UUID] = set()
            successful = True
            while len(attempted) < self._batch_size:
                deliveries = await self._claim_deliveries(
                    limit=min(self._concurrency, self._batch_size - len(attempted)),
                    exclude_ids=attempted,
                )
                if not deliveries:
                    break
                attempted.update(delivery.id for delivery in deliveries)
                try:
                    tasks = []
                    async with asyncio.TaskGroup() as group:
                        for delivery in deliveries:
                            tasks.append(
                                group.create_task(
                                    self._process_delivery_safely(delivery)
                                )
                            )
                    successful = all(task.result() for task in tasks) and successful
                finally:
                    released = await self._release_claims(deliveries)
                    successful = released and successful
            if successful:
                self._metrics.worker_success.set_to_current_time()
            return fanout_count, len(attempted)

    async def _claim_deliveries(
        self, *, limit: int, exclude_ids: set[UUID]
    ) -> list[NotificationDelivery]:
        async with asyncio.timeout(self._database_timeout_seconds):
            async with self._session_factory() as session, session.begin():
                return await SqlAlchemyNotificationDeliveryRepository(
                    session
                ).claim_pending(
                    limit=limit,
                    max_attempts=self._max_attempts,
                    lease_seconds=self._lease_seconds,
                    exclude_ids=exclude_ids,
                )

    async def _release_claims(self, deliveries: list[NotificationDelivery]) -> bool:
        try:
            async with asyncio.timeout(self._cleanup_timeout_seconds):
                async with self._session_factory() as session, session.begin():
                    repository = SqlAlchemyNotificationDeliveryRepository(session)
                    for delivery in deliveries:
                        if delivery.lease_token is not None:
                            await repository.release_lock(
                                delivery.id, delivery.lease_token
                            )
            return True
        except Exception:
            logger.exception("failed to release notification leases; awaiting expiry")
            return False

    async def _process_delivery_safely(self, delivery: NotificationDelivery) -> bool:
        try:
            return await self._process_delivery(delivery)
        except Exception:
            logger.exception("notification delivery failed delivery_id=%s", delivery.id)
            return False

    async def _process_delivery(self, delivery: NotificationDelivery) -> bool:
        if delivery.lease_token is None:
            return False
        async with asyncio.timeout(self._database_timeout_seconds):
            event, destination = await self._load_delivery_data(delivery)
        if event is None or destination is None:
            logger.warning("notification data not found delivery_id=%s", delivery.id)
            return False
        loop = asyncio.get_running_loop()
        async with asyncio.timeout(self._database_timeout_seconds):
            async with self._session_factory() as session:
                started = loop.time()
                remaining = await SqlAlchemyNotificationDeliveryRepository(
                    session
                ).remaining_lease_seconds(delivery.id, delivery.lease_token)
        if remaining is None:
            return False
        timeout = min(
            self._notification_timeout_seconds,
            remaining - (loop.time() - started) - self._database_timeout_seconds,
        )
        if timeout <= 0:
            logger.info(
                "skipped expired notification lease delivery_id=%s", delivery.id
            )
            return False
        channel = create_notification_channel(
            destination=destination,
            client=self._http_client,
            timeout_seconds=self._notification_timeout_seconds,
            public_app_url=self._public_app_url,
        )
        updated_delivery = await self._notification_service.process(
            delivery=delivery,
            event=event,
            channel=channel,
            timeout_seconds=timeout,
        )
        async with asyncio.timeout(self._database_timeout_seconds):
            async with self._session_factory() as session, session.begin():
                updated = await SqlAlchemyNotificationDeliveryRepository(
                    session
                ).update(
                    updated_delivery,
                    lease_token=delivery.lease_token,
                )
        if updated is None:
            logger.info(
                "discarded stale notification result delivery_id=%s", delivery.id
            )
        return updated is not None

    async def _load_delivery_data(
        self,
        delivery: NotificationDelivery,
    ):
        async with self._session_factory() as session:
            outbox_repository = SqlAlchemyOutboxRepository(session)

            destination_repository = SqlAlchemyNotificationDestinationRepository(
                session
            )

            event = await outbox_repository.get_by_id(delivery.event_id)

            if event is None:
                return None, None

            destination = await destination_repository.get_by_id(
                delivery.destination_id,
                organization_id=event.organization_id,
            )

            return event, destination

    async def _fan_out_pending_events(
        self,
    ) -> int:
        async with self._session_factory() as session, session.begin():
            outbox_repository = SqlAlchemyOutboxRepository(session)

            destination_repository = SqlAlchemyNotificationDestinationRepository(
                session
            )

            delivery_repository = SqlAlchemyNotificationDeliveryRepository(session)

            events = await outbox_repository.claim_pending(limit=self._batch_size)

            service = NotificationFanoutService(
                destination_repository=destination_repository,
                delivery_repository=delivery_repository,
                outbox_repository=outbox_repository,
            )

            for event in events:
                await service.fan_out(event)

            return len(events)
