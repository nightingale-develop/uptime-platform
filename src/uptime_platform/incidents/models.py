from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Uuid,
    text,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from uptime_platform.db.base import Base
from uptime_platform.incidents.entities import IncidentStatus


class IncidentModel(Base):
    __tablename__ = "incidents"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    monitor_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "monitors.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    status: Mapped[IncidentStatus] = mapped_column(
        SqlEnum(
            IncidentStatus,
            name="incident_status",
            values_callable=lambda enum_class: [item.value for item in enum_class],
        ),
        nullable=False,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index(
            "ix_incidents_resolved_at",
            "resolved_at",
            postgresql_where=text("status = 'resolved'"),
        ),
        Index(
            "ix_incidents_monitor_id_status",
            "monitor_id",
            "status",
        ),
        Index(
            "uq_incidents_one_open_per_monitor",
            "monitor_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )
