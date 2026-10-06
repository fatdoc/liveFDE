from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UploadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=255)
    byte_size: int = Field(gt=0, strict=True)
    media_type: Literal[
        "video/mp4",
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
        "audio/mp4",
        "audio/aac",
        "text/plain",
        "application/pdf",
    ]
    purpose: Literal["session_media", "transcript", "reference_pdf"]
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")

    @field_validator("filename")
    @classmethod
    def printable_filename(cls, value):
        if any(ord(char) < 32 for char in value):
            raise ValueError("Filename contains control characters")
        return value


class LinkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    material_id: UUID
    role: Literal["primary", "reference"]


class UploadOutput(BaseModel):
    upload_id: UUID
    status: Literal[
        "pending", "receiving", "uploaded", "finalizing", "available", "failed", "expired"
    ]
    max_bytes: int
    expires_at: datetime


class ReceiveOutput(BaseModel):
    upload_id: UUID
    status: Literal["uploaded"]
    received_size: int


class FinalizeOutput(BaseModel):
    material_id: UUID
    status: Literal["available"]
    sha256: str
    size_bytes: int
    deduplicated: bool


class MaterialOutput(BaseModel):
    material_id: UUID
    status: Literal["available"]
    filename: str
    purpose: Literal["session_media", "transcript", "reference_pdf"]
    media_type: str
    sha256: str
    size_bytes: int
    is_speech_evidence: Literal[False]


class LinkOutput(BaseModel):
    session_id: UUID
    material_id: UUID
    role: Literal["primary", "reference"]
    already_linked: bool


class SessionMaterialOutput(BaseModel):
    association_id: UUID
    role: Literal["primary", "reference"]
    material: MaterialOutput


class SessionMaterialsPage(BaseModel):
    items: list[SessionMaterialOutput]
    total: int
    limit: int
    offset: int
