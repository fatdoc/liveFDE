"""Tenant preferences are distinct from server-owned model routes and credentials."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    provider: Literal["local", "tencent"] = "local"
    privacy: Literal["local_only", "cloud_allowed"] = "local_only"
    allow_cloud_fallback: bool = False
    speaker: bool = False
    emotion: bool = False
    punctuation: bool = True

    @model_validator(mode="after")
    def privacy_consistency(self):
        if self.privacy == "local_only" and (self.provider != "local" or self.allow_cloud_fallback):
            raise ValueError("local_only_forbids_cloud")
        return self


class SettingsInput(Preferences):
    expected_revision: int = Field(ge=0)


class SettingsOutput(Preferences):
    revision: int = Field(ge=0)


class Authorization(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0, strict=True)
    allow_network: bool = Field(default=False, strict=True)
    max_requests: int | None = Field(default=None, ge=1, le=10, strict=True)
    max_cost_usd: float | None = Field(default=None, gt=0, le=100, allow_inf_nan=False)


class TranscriptionInput(Authorization):
    material_id: UUID
