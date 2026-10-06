"""LLM diagnostic declarations; HTTP permission is separately owned by the server."""

import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from live_review.core.provider_config import FrozenModel, ProviderRoute


def endpoint(value):
    parts = urlsplit(value)
    if (
        parts.scheme not in {"https", "http"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or any(ord(c) < 33 or ord(c) > 126 for c in value)
        or any(c in value for c in ("\\", "%", "$", "?", "#"))
        or not re.fullmatch(r"[A-Za-z0-9.-]+", parts.hostname)
        or ".." in parts.path.split("/")
        or parts.port is not None
        and not 1 <= parts.port <= 65535
        or parts.scheme == "https"
        and parts.port not in {None, 443}
    ):
        raise ValueError("invalid_endpoint")
    return value.rstrip("/")


class LLMDebugRoute(FrozenModel):
    protocol: Literal["llm_debug"] = "llm_debug"
    enabled: Literal[False] = False  # Never eligible for business analysis execution.
    base_url: str = Field(min_length=1, max_length=512)
    model: str = Field(min_length=1, max_length=128)
    key_env: Literal["LIVE_WORKSPACE_LLM_KEY"] = "LIVE_WORKSPACE_LLM_KEY"
    timeout_seconds: int = Field(default=60, ge=1, le=120)

    @field_validator("base_url")
    @classmethod
    def valid_endpoint(cls, value):
        return endpoint(value)

    @field_validator("model")
    @classmethod
    def valid_model(cls, value):
        return ProviderRoute.safe_model(value)
