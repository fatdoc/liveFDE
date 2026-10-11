"""Configuration only: no vision inference or connection-check endpoint."""

from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator

from live_review.core.model_config.llm_routes import endpoint
from live_review.core.provider_config import ProviderRoute
from live_review.modules.llm.schemas import Revision, Strict
from live_review.modules.llm.schemas import Update as TextUpdate


class Update(Revision):
    enabled: bool = Field(strict=True)
    mode: Literal["default", "independent"]
    model: str = Field(default="", max_length=128, strict=True)
    base_url: str = Field(default="", max_length=512, strict=True)
    timeout_seconds: int = Field(default=60, ge=1, le=120, strict=True)
    api_key: SecretStr | None = Field(default=None, repr=False)

    @field_validator("model")
    @classmethod
    def valid_model(cls, value):
        return ProviderRoute.safe_model(value) if value else value

    @field_validator("base_url")
    @classmethod
    def valid_url(cls, value):
        return endpoint(value) if value else value

    @field_validator("api_key")
    @classmethod
    def valid_key(cls, value):
        return TextUpdate.valid_key(value)

    @model_validator(mode="after")
    def required_fields(self):
        if self.enabled and not self.model:
            raise ValueError("vision_model_required")
        if self.mode == "independent" and not self.base_url:
            raise ValueError("vision_endpoint_required")
        if self.mode == "default" and self.api_key is not None:
            raise ValueError("default_service_key_is_reference_only")
        return self


class Stored(Strict):
    revision: str = "0"
    enabled: bool = False
    mode: Literal["default", "independent"] = "default"
    model: str = ""
    base_url: str = ""
    timeout_seconds: int = 60
    independent_key_configured: bool = False


class Public(Stored):
    protocol: Literal["openai_compatible"] = "openai_compatible"
    configured: bool = False
    effective_base_url: str = ""
    default_revision: str | None = None
    default_status: str | None = None
    debug_http: bool = False
    analysis_enabled: Literal[False] = False
    verification: Literal["not_tested"] = "not_tested"
