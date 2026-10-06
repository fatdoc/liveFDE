from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_serializer

from live_review.core.model_config.llm_routes import endpoint
from live_review.core.provider_config import ProviderRoute


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class Revision(Strict):
    expected_revision: str = Field(min_length=1, max_length=64, strict=True)


class Update(Revision):
    base_url: str = Field(min_length=1, max_length=512, strict=True)
    model: str = Field(min_length=1, max_length=128, strict=True)
    timeout_seconds: int = Field(ge=1, le=120, strict=True)
    api_key: SecretStr | None = Field(default=None, repr=False)

    @field_validator("base_url")
    @classmethod
    def valid_url(cls, value):
        return endpoint(value)

    @field_validator("model")
    @classmethod
    def valid_model(cls, value):
        return ProviderRoute.safe_model(value)

    @field_validator("api_key")
    @classmethod
    def valid_key(cls, value):
        if value is None:
            raise ValueError("key_must_be_omitted_or_nonempty")
        text = value.get_secret_value()
        if not text or len(text) > 4096 or any(ord(c) < 33 or ord(c) > 126 for c in text):
            raise ValueError("invalid_key")
        return value


class Check(Revision):
    request_id: UUID


class Usage(Strict):
    prompt_tokens: int | None = Field(default=None, ge=0, le=1000000000)
    completion_tokens: int | None = Field(default=None, ge=0, le=1000000000)
    total_tokens: int | None = Field(default=None, ge=0, le=1000000000)

    @model_serializer
    def supplied_fields(self):
        return {key: value for key, value in vars(self).items() if value is not None}


class Public(Strict):
    revision: str = "0"
    base_url: str = ""
    model: str = ""
    timeout_seconds: int = 60
    configured: bool = False
    status: Literal[
        "not_configured", "unverified", "checking", "verified", "check_failed", "unknown"
    ] = "not_configured"
    checked_at: str | None = None
    last_error: str | None = None
    usage: Usage | None = None
    debug_http: bool = False
    analysis_enabled: Literal[False] = False


class Record(Strict):
    revision: str
    result: Public


class State(Strict):
    value: Public = Field(default_factory=Public)
    requests: dict[str, Record] = Field(default_factory=dict)
