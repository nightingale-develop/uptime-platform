from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import ValidationError

from uptime_platform.monitors.entities import (
    DnsMonitorConfig,
    HttpMethod,
    HttpMonitorConfig,
    IcmpMonitorConfig,
    Monitor,
    MonitorConfig,
    MonitorStatus,
    TcpMonitorConfig,
    TlsMonitorConfig,
)
from uptime_platform.monitors.exceptions import (
    InvalidMonitorConfigError,
)
from uptime_platform.monitors.protocols import (
    MonitorRepositoryProtocol,
)
from uptime_platform.monitors.schemas import (
    DnsMonitorConfigCreate,
    DnsMonitorConfigUpdate,
    HttpMonitorConfigCreate,
    HttpMonitorConfigUpdate,
    IcmpMonitorConfigCreate,
    IcmpMonitorConfigUpdate,
    MonitorCreate,
    MonitorUpdate,
    TcpMonitorConfigCreate,
    TcpMonitorConfigUpdate,
    TlsMonitorConfigCreate,
    TlsMonitorConfigUpdate,
)


def _validate_update(
    model: type[
        HttpMonitorConfigUpdate
        | TcpMonitorConfigUpdate
        | DnsMonitorConfigUpdate
        | TlsMonitorConfigUpdate
        | IcmpMonitorConfigUpdate
    ],
    data: dict[str, object],
):
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise InvalidMonitorConfigError(str(exc)) from exc


def _create_config(
    config: (
        HttpMonitorConfigCreate
        | TcpMonitorConfigCreate
        | DnsMonitorConfigCreate
        | TlsMonitorConfigCreate
        | IcmpMonitorConfigCreate
    ),
) -> MonitorConfig:
    if isinstance(
        config,
        HttpMonitorConfigCreate,
    ):
        return HttpMonitorConfig(
            url=str(config.url),
            method=config.method,
            expected_status_codes=(
                tuple(config.expected_status_codes)
                if config.expected_status_codes is not None
                else None
            ),
            body_contains=config.body_contains,
            follow_redirects=config.follow_redirects,
            verify_tls=config.verify_tls,
        )

    if isinstance(
        config,
        TcpMonitorConfigCreate,
    ):
        return TcpMonitorConfig(
            host=config.host,
            port=config.port,
        )

    if isinstance(
        config,
        DnsMonitorConfigCreate,
    ):
        return DnsMonitorConfig(
            host=config.host,
            record_type=config.record_type,
        )

    if isinstance(
        config,
        TlsMonitorConfigCreate,
    ):
        return TlsMonitorConfig(
            host=config.host,
            port=config.port,
            expiry_threshold_days=config.expiry_threshold_days,
        )

    if isinstance(
        config,
        IcmpMonitorConfigCreate,
    ):
        return IcmpMonitorConfig(
            host=config.host,
        )

    raise TypeError(f"Unsupported monitor config: {type(config)}")


def _update_config(
    current: MonitorConfig,
    data: dict[str, object],
) -> MonitorConfig:
    try:
        return _update_config_validated(
            current=current,
            data=data,
        )
    except ValidationError as exc:
        raise InvalidMonitorConfigError(str(exc)) from exc


def _update_config_validated(
    current: MonitorConfig,
    data: dict[str, object],
) -> MonitorConfig:
    if isinstance(
        current,
        HttpMonitorConfig,
    ):
        update = HttpMonitorConfigUpdate.model_validate(data)

        expected_status_codes = current.expected_status_codes

        if "expected_status_codes" in update.model_fields_set:
            expected_status_codes = (
                tuple(update.expected_status_codes)
                if update.expected_status_codes is not None
                else None
            )

        body_contains = current.body_contains

        if "body_contains" in update.model_fields_set:
            body_contains = update.body_contains

        updated_config = HttpMonitorConfig(
            url=(str(update.url) if update.url is not None else current.url),
            method=(update.method if update.method is not None else current.method),
            expected_status_codes=expected_status_codes,
            body_contains=body_contains,
            follow_redirects=(
                update.follow_redirects
                if update.follow_redirects is not None
                else current.follow_redirects
            ),
            verify_tls=(
                update.verify_tls
                if update.verify_tls is not None
                else current.verify_tls
            ),
        )

        if (
            updated_config.method is HttpMethod.HEAD
            and updated_config.body_contains is not None
        ):
            raise InvalidMonitorConfigError("HEAD monitor cannot use body_contains")

        return updated_config

    if isinstance(
        current,
        TcpMonitorConfig,
    ):
        update = TcpMonitorConfigUpdate.model_validate(data)

        return TcpMonitorConfig(
            host=(update.host if update.host is not None else current.host),
            port=(update.port if update.port is not None else current.port),
        )

    if isinstance(
        current,
        DnsMonitorConfig,
    ):
        update = DnsMonitorConfigUpdate.model_validate(data)

        return DnsMonitorConfig(
            host=(update.host if update.host is not None else current.host),
            record_type=(
                update.record_type
                if update.record_type is not None
                else current.record_type
            ),
        )

    if isinstance(
        current,
        TlsMonitorConfig,
    ):
        update = TlsMonitorConfigUpdate.model_validate(data)

        return TlsMonitorConfig(
            host=(update.host if update.host is not None else current.host),
            port=(update.port if update.port is not None else current.port),
            expiry_threshold_days=(
                update.expiry_threshold_days
                if update.expiry_threshold_days is not None
                else current.expiry_threshold_days
            ),
        )

    if isinstance(
        current,
        IcmpMonitorConfig,
    ):
        update = IcmpMonitorConfigUpdate.model_validate(data)

        return IcmpMonitorConfig(
            host=(update.host if update.host is not None else current.host),
        )

    raise TypeError(f"Unsupported monitor config: {type(current)}")


class MonitorService:
    def __init__(
        self,
        repository: MonitorRepositoryProtocol,
        organization_id: UUID,
    ) -> None:
        self._repository = repository
        self._organization_id = organization_id

    async def create(
        self,
        data: MonitorCreate,
    ) -> Monitor:
        now = datetime.now(UTC)

        monitor = Monitor(
            id=uuid4(),
            organization_id=self._organization_id,
            name=data.name,
            monitor_type=data.monitor_type,
            config=_create_config(data.config),
            interval_seconds=data.interval_seconds,
            timeout_seconds=data.timeout_seconds,
            status=MonitorStatus.PENDING,
            created_at=now,
            next_check_at=now,
            failure_threshold=data.failure_threshold,
            recovery_threshold=data.recovery_threshold,
        )

        return await self._repository.create(monitor)

    async def get_all(
        self,
    ) -> list[Monitor]:
        return await self._repository.get_all(self._organization_id)

    async def get_by_id(
        self,
        monitor_id: UUID,
    ) -> Monitor | None:
        return await self._repository.get_by_id(
            monitor_id,
            self._organization_id,
        )

    async def update(
        self,
        monitor_id: UUID,
        data: MonitorUpdate,
    ) -> Monitor | None:
        monitor = await self._repository.get_by_id_for_update(
            monitor_id,
            organization_id=self._organization_id,
        )

        if monitor is None:
            return None

        config = monitor.config

        if data.config is not None:
            try:
                config = _update_config(
                    current=monitor.config,
                    data=data.config,
                )
            except ValidationError as exc:
                raise InvalidMonitorConfigError(str(exc)) from exc

        updated_monitor = replace(
            monitor,
            name=(data.name if data.name is not None else monitor.name),
            config=config,
            interval_seconds=(
                data.interval_seconds
                if data.interval_seconds is not None
                else monitor.interval_seconds
            ),
            timeout_seconds=(
                data.timeout_seconds
                if data.timeout_seconds is not None
                else monitor.timeout_seconds
            ),
            failure_threshold=(
                data.failure_threshold
                if data.failure_threshold is not None
                else monitor.failure_threshold
            ),
            recovery_threshold=(
                data.recovery_threshold
                if data.recovery_threshold is not None
                else monitor.recovery_threshold
            ),
        )

        return await self._repository.update(updated_monitor)

    async def delete(
        self,
        monitor_id: UUID,
    ) -> bool:
        return await self._repository.delete(
            monitor_id,
            self._organization_id,
        )
