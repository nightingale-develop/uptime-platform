from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class OutboxEventType(StrEnum):
    INCIDENT_OPENED = "incident_opened"
    INCIDENT_RESOLVED = "incident_resolved"


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    id: UUID
    organization_id: UUID
    event_type: OutboxEventType
    payload: dict[str, object]
    created_at: datetime
    processed_at: datetime | None
