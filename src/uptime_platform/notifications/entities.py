from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class NotificationDestinationType(StrEnum):
    WEBHOOK = "webhook"
    TELEGRAM = "telegram"
    EMAIL = "email"
    SLACK = "slack"


class EmailSecurity(StrEnum):
    NONE = "none"
    STARTTLS = "starttls"
    TLS = "tls"


@dataclass(frozen=True, slots=True)
class WebhookDestinationConfig:
    url: str
    secret: str


@dataclass(frozen=True, slots=True)
class TelegramDestinationConfig:
    bot_token: str
    chat_id: str


@dataclass(frozen=True, slots=True)
class SlackDestinationConfig:
    webhook_url: str


@dataclass(frozen=True, slots=True)
class EmailDestinationConfig:
    host: str
    port: int
    username: str | None
    password: str | None
    from_email: str
    to_email: str
    security: EmailSecurity


type NotificationDestinationConfig = (
    WebhookDestinationConfig
    | TelegramDestinationConfig
    | EmailDestinationConfig
    | SlackDestinationConfig
)


@dataclass(frozen=True, slots=True)
class NotificationDestination:
    id: UUID
    organization_id: UUID
    name: str
    destination_type: NotificationDestinationType
    enabled: bool
    config: NotificationDestinationConfig
    created_at: datetime


@dataclass(frozen=True, slots=True)
class NotificationDelivery:
    id: UUID
    event_id: UUID
    destination_id: UUID
    created_at: datetime
    processed_at: datetime | None
    attempts: int
    last_error: str | None
    next_attempt_at: datetime
    locked_until: datetime | None
    lease_token: UUID | None = None
