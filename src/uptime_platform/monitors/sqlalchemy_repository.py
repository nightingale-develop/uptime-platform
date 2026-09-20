from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from uptime_platform.monitors.entities import (
    DnsMonitorConfig,
    DnsRecordType,
    HttpMethod,
    HttpMonitorConfig,
    IcmpMonitorConfig,
    Monitor,
    MonitorClaim,
    MonitorConfig,
    MonitorStatus,
    MonitorType,
    TcpMonitorConfig,
    TlsMonitorConfig,
)
from uptime_platform.monitors.models import (
    MonitorModel,
)


class SqlAlchemyMonitorRepository:
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def create(
        self,
        monitor: Monitor,
    ) -> Monitor:
        model = MonitorModel(
            id=monitor.id,
            organization_id=monitor.organization_id,
            name=monitor.name,
            monitor_type=monitor.monitor_type,
            config=self._config_to_dict(monitor.config),
            interval_seconds=monitor.interval_seconds,
            timeout_seconds=monitor.timeout_seconds,
            status=monitor.status,
            created_at=monitor.created_at,
            next_check_at=monitor.next_check_at,
            failure_threshold=monitor.failure_threshold,
            recovery_threshold=monitor.recovery_threshold,
            consecutive_failures=monitor.consecutive_failures,
            consecutive_successes=monitor.consecutive_successes,
        )

        self._session.add(model)

        await self._session.flush()
        await self._session.refresh(model)

        return self._to_entity(model)

    async def get_all(
        self,
        organization_id: UUID,
    ) -> list[Monitor]:
        statement = (
            select(MonitorModel)
            .where(MonitorModel.organization_id == organization_id)
            .order_by(MonitorModel.created_at)
        )

        result = await self._session.execute(statement)

        return [self._to_entity(model) for model in result.scalars().all()]

    async def get_by_id(
        self,
        monitor_id: UUID,
        organization_id: UUID,
    ) -> Monitor | None:
        statement = select(MonitorModel).where(
            MonitorModel.id == monitor_id,
            MonitorModel.organization_id == organization_id,
        )

        result = await self._session.execute(statement)

        model = result.scalar_one_or_none()

        if model is None:
            return None

        return self._to_entity(model)

    async def get_by_id_for_update(
        self,
        monitor_id: UUID,
        *,
        organization_id: UUID | None = None,
        lease_token: UUID | None = None,
    ) -> Monitor | None:
        statement = (
            select(MonitorModel)
            .where(MonitorModel.id == monitor_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

        if organization_id is not None:
            statement = statement.where(MonitorModel.organization_id == organization_id)

        result = await self._session.execute(statement)

        model = result.scalar_one_or_none()

        if model is None:
            return None

        if lease_token is not None:
            # Read the clock AFTER acquiring the lock, including any lock wait.
            now = await self._session.scalar(select(func.clock_timestamp()))
            if (
                model.check_lease_token != lease_token
                or model.check_lease_until is None
                or model.check_lease_until <= now
            ):
                return None

        return self._to_entity(model)

    async def claim_due(
        self,
        *,
        limit: int,
        lease_grace_seconds: float,
        exclude_ids: set[UUID] | None = None,
    ) -> list[MonitorClaim]:
        """Reserve due monitors; caller must commit before starting network IO."""
        if limit < 1 or lease_grace_seconds <= 0:
            raise ValueError("Claim limit and lease grace must be positive")

        statement = (
            select(MonitorModel)
            .where(
                MonitorModel.next_check_at <= func.clock_timestamp(),
                MonitorModel.status != MonitorStatus.PAUSED,
                or_(
                    MonitorModel.check_lease_until.is_(None),
                    MonitorModel.check_lease_until <= func.clock_timestamp(),
                ),
            )
            .order_by(MonitorModel.next_check_at, MonitorModel.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        if exclude_ids:
            statement = statement.where(MonitorModel.id.not_in(exclude_ids))

        models = (await self._session.scalars(statement)).all()
        now = await self._session.scalar(select(func.clock_timestamp()))
        claims = []
        for model in models:
            model.check_lease_token = uuid4()
            model.check_lease_until = now + timedelta(
                seconds=model.timeout_seconds + lease_grace_seconds,
            )
            claims.append(
                MonitorClaim(
                    monitor=self._to_entity(model),
                    token=model.check_lease_token,
                    expires_at=model.check_lease_until,
                )
            )
        await self._session.flush()
        return claims

    async def release_check_lease(self, monitor_id: UUID, token: UUID) -> bool:
        result = await self._session.execute(
            update(MonitorModel)
            .where(
                MonitorModel.id == monitor_id,
                MonitorModel.check_lease_token == token,
            )
            .values(check_lease_token=None, check_lease_until=None)
            .returning(MonitorModel.id)
        )
        return result.scalar_one_or_none() is not None

    async def update(
        self,
        monitor: Monitor,
    ) -> Monitor | None:
        model = await self._session.get(
            MonitorModel,
            monitor.id,
        )

        if model is None:
            return None

        model.name = monitor.name
        model.monitor_type = monitor.monitor_type
        model.config = self._config_to_dict(monitor.config)
        model.interval_seconds = monitor.interval_seconds
        model.timeout_seconds = monitor.timeout_seconds
        model.status = monitor.status
        model.next_check_at = monitor.next_check_at
        model.failure_threshold = monitor.failure_threshold
        model.recovery_threshold = monitor.recovery_threshold
        model.consecutive_failures = monitor.consecutive_failures
        model.consecutive_successes = monitor.consecutive_successes

        await self._session.flush()
        await self._session.refresh(model)

        return self._to_entity(model)

    async def delete(
        self,
        monitor_id: UUID,
        organization_id: UUID,
    ) -> bool:
        statement = select(MonitorModel).where(
            MonitorModel.id == monitor_id,
            MonitorModel.organization_id == organization_id,
        )

        result = await self._session.execute(statement)

        model = result.scalar_one_or_none()

        if model is None:
            return False

        await self._session.delete(model)
        await self._session.flush()

        return True

    async def get_due(
        self,
        now: datetime,
        limit: int,
    ) -> list[Monitor]:
        statement = (
            select(MonitorModel)
            .where(
                MonitorModel.next_check_at <= now,
                MonitorModel.status != MonitorStatus.PAUSED,
            )
            .order_by(MonitorModel.next_check_at)
            .limit(limit)
        )

        result = await self._session.execute(statement)

        models = result.scalars().all()

        return [self._to_entity(model) for model in models]

    @staticmethod
    def _config_to_dict(
        config: MonitorConfig,
    ) -> dict[str, object]:
        if isinstance(
            config,
            HttpMonitorConfig,
        ):
            return {
                "url": config.url,
                "method": config.method.value,
                "expected_status_codes": (
                    list(config.expected_status_codes)
                    if config.expected_status_codes is not None
                    else None
                ),
                "body_contains": config.body_contains,
                "follow_redirects": config.follow_redirects,
                "verify_tls": config.verify_tls,
            }

        if isinstance(
            config,
            TcpMonitorConfig,
        ):
            return {
                "host": config.host,
                "port": config.port,
            }

        if isinstance(
            config,
            DnsMonitorConfig,
        ):
            return {
                "host": config.host,
                "record_type": config.record_type.value,
            }

        if isinstance(
            config,
            TlsMonitorConfig,
        ):
            return {
                "host": config.host,
                "port": config.port,
                "expiry_threshold_days": config.expiry_threshold_days,
            }

        if isinstance(
            config,
            IcmpMonitorConfig,
        ):
            return {
                "host": config.host,
            }

        raise TypeError(f"Unsupported monitor config: {type(config)}")

    @staticmethod
    def _to_entity(
        model: MonitorModel,
    ) -> Monitor:
        if model.monitor_type is MonitorType.HTTP:
            raw_status_codes = model.config.get("expected_status_codes")

            config = HttpMonitorConfig(
                url=str(model.config["url"]),
                method=HttpMethod(
                    str(
                        model.config.get(
                            "method",
                            HttpMethod.GET.value,
                        )
                    )
                ),
                expected_status_codes=(
                    tuple(int(status_code) for status_code in raw_status_codes)
                    if raw_status_codes is not None
                    else None
                ),
                body_contains=(
                    str(model.config["body_contains"])
                    if model.config.get("body_contains") is not None
                    else None
                ),
                follow_redirects=bool(
                    model.config.get(
                        "follow_redirects",
                        False,
                    )
                ),
                verify_tls=bool(
                    model.config.get(
                        "verify_tls",
                        True,
                    )
                ),
            )

        elif model.monitor_type is MonitorType.TCP:
            config = TcpMonitorConfig(
                host=str(model.config["host"]),
                port=int(model.config["port"]),
            )

        elif model.monitor_type is MonitorType.DNS:
            config = DnsMonitorConfig(
                host=str(model.config["host"]),
                record_type=DnsRecordType(str(model.config["record_type"])),
            )

        elif model.monitor_type is MonitorType.TLS:
            config = TlsMonitorConfig(
                host=str(model.config["host"]),
                port=int(
                    model.config.get(
                        "port",
                        443,
                    )
                ),
                expiry_threshold_days=int(
                    model.config.get(
                        "expiry_threshold_days",
                        14,
                    )
                ),
            )

        elif model.monitor_type is MonitorType.ICMP:
            config = IcmpMonitorConfig(
                host=str(model.config["host"]),
            )

        else:
            raise ValueError(f"Unsupported monitor type: {model.monitor_type}")

        return Monitor(
            id=model.id,
            organization_id=model.organization_id,
            name=model.name,
            monitor_type=model.monitor_type,
            config=config,
            interval_seconds=model.interval_seconds,
            timeout_seconds=model.timeout_seconds,
            status=model.status,
            created_at=model.created_at,
            next_check_at=model.next_check_at,
            failure_threshold=model.failure_threshold,
            recovery_threshold=model.recovery_threshold,
            consecutive_failures=model.consecutive_failures,
            consecutive_successes=model.consecutive_successes,
        )
