from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from uptime_platform.db.base import Base
from uptime_platform.notifications.entities import (
    NotificationDestinationType,
)


class NotificationDestinationModel(Base):
    __tablename__ = "notification_destinations"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
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

    destination_type: Mapped[NotificationDestinationType] = mapped_column(
        Enum(
            NotificationDestinationType,
            name="notification_destination_type",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    config: Mapped[dict[str, str]] = mapped_column(
        JSONB,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


class NotificationDeliveryModel(Base):
    __tablename__ = "notification_deliveries"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
    )

    event_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "outbox_events.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    destination_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "notification_destinations.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    last_error: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
    )

    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    lease_token: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "lease_token IS NULL OR locked_until IS NOT NULL",
            name="ck_notification_delivery_lease_expiry",
        ),
        UniqueConstraint(
            "event_id",
            "destination_id",
            name="uq_notification_delivery_event_destination",
        ),
        Index(
            "ix_notification_deliveries_pending",
            "processed_at",
            "next_attempt_at",
            "locked_until",
        ),
    )
