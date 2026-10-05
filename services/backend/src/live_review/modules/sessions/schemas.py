from datetime import date, datetime
from typing import Annotated, Literal, Self
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from live_review.modules.streamers.schemas import Platform

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Precision = Literal["date", "minute", "second"]


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    streamer_id: UUID
    title: Title
    platform: Platform
    session_local_date: date
    started_at: AwareDatetime | None = None
    time_precision: Precision = "date"
    timezone: Literal["Asia/Shanghai"] = "Asia/Shanghai"

    @model_validator(mode="after")
    def validate_time(self) -> Self:
        if (self.time_precision == "date") != (self.started_at is None):
            raise ValueError("Date precision requires null time; known precision requires time")
        if self.started_at is not None:
            local = self.started_at.astimezone(ZoneInfo(self.timezone))
            if local.date() != self.session_local_date:
                raise ValueError("Start time does not match local session date")
            if local.microsecond or (self.time_precision == "minute" and local.second):
                raise ValueError("Time is more precise than declared")
        return self


class SessionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1, strict=True)
    title: Title | None = None
    streamer_id: UUID | None = None
    session_local_date: date | None = None
    started_at: AwareDatetime | None = None
    time_precision: Precision | None = None

    @model_validator(mode="after")
    def reject_null_fields(self) -> Self:
        for name in self.model_fields_set - {"started_at"}:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        if self.model_fields_set == {"expected_revision"}:
            raise ValueError("At least one changed field is required")
        return self


class SessionView(SessionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    revision: int
    time_source: Literal["user_entered", "media_metadata"]
    duration_ms: int | None
    processing_status: str
    created_at: datetime
    updated_at: datetime


class SessionList(BaseModel):
    items: list[SessionView]
    total: int
    limit: int
    offset: int
