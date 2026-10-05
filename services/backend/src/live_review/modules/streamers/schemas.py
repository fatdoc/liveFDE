from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

Platform = Literal["douyin", "wechat", "other"]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class StreamerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    platform: Platform
    platform_ref: Annotated[str, StringConstraints(max_length=200)] | None = None


class StreamerView(StreamerCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime


class StreamerList(BaseModel):
    items: list[StreamerView]
    total: int
    limit: int
    offset: int
