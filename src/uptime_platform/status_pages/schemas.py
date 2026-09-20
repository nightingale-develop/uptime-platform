from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from uptime_platform.monitors.entities import MonitorStatus
from uptime_platform.status_pages.entities import StatusPageStatus


class StatusPageCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=100,
    )
    slug: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    published: bool = True


class StatusPageUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    published: bool | None = None

    @field_validator("name", "published")
    @classmethod
    def reject_null(cls, value: str | bool | None) -> str | bool:
        if value is None:
            raise ValueError("This field cannot be null")
        return value


class StatusPageResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    published: bool


class StatusPageMonitorResponse(BaseModel):
    id: UUID
    name: str
    status: MonitorStatus


class PublicStatusPageResponse(BaseModel):
    name: str
    slug: str
    status: StatusPageStatus
    monitors: list[StatusPageMonitorResponse]
