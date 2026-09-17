from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Uuid,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from uptime_platform.db.base import Base
from uptime_platform.monitors.entities import (
    MonitorStatus,
    MonitorType,
)


class MonitorModel(Base):
    __tablename__ = "monitors"

    __table_args__ = (
        CheckConstraint(
            "(check_lease_token IS NULL) = (check_lease_until IS NULL)",
            name="ck_monitors_check_lease_pair",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    monitor_type: Mapped[MonitorType] = mapped_column(
        SqlEnum(
            MonitorType,
            name="monitor_type",
            values_callable=lambda enum_class: [item.value for item in enum_class],
        ),
        nullable=False,
    )

    config: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
    )

    interval_seconds: Mapped[int] = mapped_column(
        nullable=False,
        default=60,
    )

    timeout_seconds: Mapped[int] = mapped_column(
        nullable=False,
        default=5,
    )

    status: Mapped[MonitorStatus] = mapped_column(
        SqlEnum(
            MonitorStatus,
            name="monitor_status",
            values_callable=lambda enum_class: [item.value for item in enum_class],
        ),
        nullable=False,
        default=MonitorStatus.PENDING,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    next_check_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    check_lease_token: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    check_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    failure_threshold: Mapped[int] = mapped_column(
        nullable=False,
        default=3,
    )

    recovery_threshold: Mapped[int] = mapped_column(
        nullable=False,
        default=2,
    )

    consecutive_failures: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
    )

    consecutive_successes: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
    )
