from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class MonitorStatistics:
    monitor_id: UUID
    starts_at: datetime
    ends_at: datetime
    total_checks: int
    successful_checks: int
    failed_checks: int
    uptime_percentage: float | None
    average_response_time_ms: float | None
    history_available_from: datetime | None = None
    first_check_at: datetime | None = None
    last_check_at: datetime | None = None
    is_partial: bool = False
