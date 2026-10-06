"""Provider boundary: ephemeral URLs never belong to business records."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CaptureError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class StopCapture(Exception):
    pass


@dataclass
class Source:
    live: bool
    url: str | None = field(default=None, repr=False)


class Provider(Protocol):
    def probe(self, reference: str, tick) -> Source: ...
    def acquire(self, reference: str, tick) -> Source: ...
    def health(self) -> dict: ...


# Manifest is a closed, non-secret handoff contract, not arbitrary provider JSON.


class CaptureManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    platform: Literal["douyin", "wechat"]
    capture_run_id: UUID
    source_ref: str = Field(max_length=200)
    started_at: datetime
    ended_at: datetime
    duration_ms: int = Field(gt=0, le=172800000, strict=True)
    sha256: str = Field(pattern="^[a-f0-9]{64}$")
    size_bytes: int = Field(gt=0, strict=True)
    media_types: list[str]
    file: Literal["recording.mp4"]
    segment_index: Literal[0]
    complete: bool = Field(strict=True)
    end_reason: str = Field(pattern="^[a-z][a-z0-9_]{0,79}$")
    closed: Literal[True]

    @model_validator(mode="after")
    def verify_media(self):
        if (
            self.started_at.tzinfo is None
            or self.ended_at.tzinfo is None
            or self.ended_at < self.started_at
            or not {"audio", "video"} <= set(self.media_types)
        ):
            raise ValueError("invalid_closed_media_manifest")
        return self
