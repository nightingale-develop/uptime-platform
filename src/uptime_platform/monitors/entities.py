from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class MonitorStatus(StrEnum):
    PENDING = "pending"
    UP = "up"
    DOWN = "down"
    PAUSED = "paused"


class MonitorType(StrEnum):
    HTTP = "http"
    TCP = "tcp"
    DNS = "dns"
    TLS = "tls"
    ICMP = "icmp"


class HttpMethod(StrEnum):
    GET = "GET"
    HEAD = "HEAD"


class DnsRecordType(StrEnum):
    A = "A"
    AAAA = "AAAA"
    CNAME = "CNAME"
    MX = "MX"
    TXT = "TXT"


@dataclass(frozen=True, slots=True)
class HttpMonitorConfig:
    url: str
    method: HttpMethod = HttpMethod.GET
    expected_status_codes: tuple[int, ...] | None = None
    body_contains: str | None = None
    follow_redirects: bool = False
    verify_tls: bool = True


@dataclass(frozen=True, slots=True)
class TcpMonitorConfig:
    host: str
    port: int


@dataclass(frozen=True, slots=True)
class DnsMonitorConfig:
    host: str
    record_type: DnsRecordType


@dataclass(frozen=True, slots=True)
class TlsMonitorConfig:
    host: str
    port: int = 443
    expiry_threshold_days: int = 14


@dataclass(frozen=True, slots=True)
class IcmpMonitorConfig:
    host: str


type MonitorConfig = (
    HttpMonitorConfig
    | TcpMonitorConfig
    | DnsMonitorConfig
    | TlsMonitorConfig
    | IcmpMonitorConfig
)


@dataclass(frozen=True, slots=True)
class Monitor:
    id: UUID
    organization_id: UUID
    name: str
    monitor_type: MonitorType
    config: MonitorConfig
    interval_seconds: int
    timeout_seconds: int
    status: MonitorStatus
    created_at: datetime
    next_check_at: datetime
    failure_threshold: int = 3
    recovery_threshold: int = 2
    consecutive_failures: int = 0
    consecutive_successes: int = 0


@dataclass(frozen=True, slots=True)
class MonitorClaim:
    monitor: Monitor
    token: UUID
    expires_at: datetime
