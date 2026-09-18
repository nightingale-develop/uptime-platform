from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from uptime_platform.db.base import Base


class CheckModel(Base):
    __tablename__ = "checks"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    monitor_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "monitors.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    success: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )

    response_time_ms: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    status_code: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    details: Mapped[dict[str, object] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_checks_checked_at", "checked_at"),
        Index(
            "ix_checks_monitor_id_checked_at",
            "monitor_id",
            "checked_at",
        ),
    )
