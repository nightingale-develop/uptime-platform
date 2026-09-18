from functools import lru_cache

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    database_url: str

    retention_enabled: bool = True
    retention_checks_days: int = Field(default=30, ge=1, le=36500)
    retention_incidents_days: int = Field(default=90, ge=1, le=36500)
    retention_notifications_days: int = Field(default=30, ge=1, le=36500)
    retention_interval_seconds: int = Field(default=60, ge=1)
    retention_batch_size: int = Field(default=1000, ge=1, le=100000)

    notification_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        le=60,
    )

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
