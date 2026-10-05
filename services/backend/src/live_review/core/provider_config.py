"""YAML is the sole provider policy source; no network/provider discovery here."""

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from yaml.events import (
    AliasEvent,
    MappingEndEvent,
    MappingStartEvent,
    SequenceEndEvent,
    SequenceStartEvent,
)

MAX_BYTES = 65536
Capability = Literal["asr", "text", "vision"]


class ProviderConfigError(ValueError):
    """Stable codes only: do not attach raw parser errors, paths or configuration."""


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, hide_input_in_errors=True)


class MediaConfig(FrozenModel):
    segment_seconds: int = Field(default=300, ge=1, le=900)
    ffmpeg_timeout_seconds: int = Field(default=600, ge=1, le=3600)
    ffprobe_timeout_seconds: int = Field(default=30, ge=1, le=120)
    sample_rate: Literal[16000] = 16000
    channels: Literal[1] = 1
    max_duration_seconds: int = Field(default=14400, ge=1, le=86400)

    @field_validator("sample_rate", "channels", mode="before")
    @classmethod
    def integer_constants(cls, value):
        if type(value) is not int:
            raise ValueError("integer_required")
        return value


class ProviderRoute(FrozenModel):
    enabled: bool = False
    protocol: Literal["disabled", "offline_fixture", "openai_compatible"] = "disabled"
    provider: str | None = Field(default=None, max_length=64, pattern=r"^[a-z][a-z0-9_-]*$")
    model: str | None = Field(default=None, min_length=1, max_length=128)
    base_url: str | None = Field(default=None, max_length=512)
    key_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,127}$")
    timeout_seconds: int = Field(default=60, ge=1, le=600)
    max_requests: int = Field(default=0, ge=0, le=10000)
    max_cost_usd: float = Field(default=0.0, ge=0, le=1000, allow_inf_nan=False)

    @field_validator("model")
    @classmethod
    def safe_model(cls, value):
        if value is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:-]{0,127}", value):
            raise ValueError("invalid_model")
        return value

    @field_validator("base_url")
    @classmethod
    def safe_url(cls, value):
        if value is None:
            return value
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.port not in (None, 443)
            or any(c.isspace() for c in value)
            or "\\" in value
            or "%" in value
            or not re.fullmatch(r"[a-zA-Z0-9.-]+", url.hostname)
            or ".." in url.path.split("/")
            or "$" in value
        ):
            raise ValueError("invalid_endpoint")
        return value.rstrip("/")

    @model_validator(mode="after")
    def coherent_route(self):
        if not self.enabled:
            if (
                self.protocol != "disabled"
                or any(
                    value is not None
                    for value in (self.provider, self.model, self.base_url, self.key_env)
                )
                or self.max_requests
                or self.max_cost_usd
            ):
                raise ValueError("disabled_route_has_configuration")
        elif self.protocol == "offline_fixture":
            if (
                self.provider != "synthetic"
                or self.model != "fixture-v1"
                or self.base_url is not None
                or self.key_env is not None
                or self.max_requests < 1
                or self.max_cost_usd != 0
            ):
                raise ValueError("invalid_fixture_route")
        elif self.protocol == "openai_compatible":
            if not all((self.provider, self.model, self.base_url, self.key_env)):
                raise ValueError("incomplete_route")
            if self.max_requests < 1 or self.max_cost_usd <= 0:
                raise ValueError("unconfigured_budget")
        else:
            raise ValueError("enabled_route_requires_protocol")
        return self


class Providers(FrozenModel):
    asr: ProviderRoute = Field(default_factory=ProviderRoute)
    text: ProviderRoute = Field(default_factory=ProviderRoute)
    vision: ProviderRoute = Field(default_factory=ProviderRoute)

    @model_validator(mode="after")
    def fixture_asr_only(self):
        if any(route.protocol == "offline_fixture" for route in (self.text, self.vision)):
            raise ValueError("fixture_only_supports_asr")
        return self


class ProviderConfig(FrozenModel):
    schema_version: Literal[1] = 1
    revision: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")
    media: MediaConfig = Field(default_factory=MediaConfig)
    providers: Providers = Field(default_factory=Providers)


class ConfigSnapshot(FrozenModel):
    snapshot_version: Literal[1] = 1
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    content: ProviderConfig

    @model_validator(mode="after")
    def validate_fingerprint(self):
        if self.config_hash != fingerprint(self.content):
            raise ValueError("snapshot_fingerprint_mismatch")
        return self


class ExecutionRoute(FrozenModel):
    capability: Capability
    route: ProviderRoute
    config_hash: str
    synthetic: bool
    api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)


class StrictLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise ProviderConfigError("invalid_mapping")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def validate_environment(config: ProviderConfig, environment: str):
    if environment not in {"development", "test", "production"}:
        raise ProviderConfigError("invalid_environment")
    if environment == "production" and config.providers.asr.protocol == "offline_fixture":
        raise ProviderConfigError("synthetic_forbidden_in_production")


def load_config(path: Path, *, environment: str = "development") -> ProviderConfig:
    """Explicit absolute regular file only; no interpolation, symlinks or remote paths."""
    try:
        path = Path(path)
        if not path.is_absolute() or path.resolve() != path or "$" in str(path):
            raise ProviderConfigError("invalid_config_path")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ProviderConfigError("invalid_config_path")
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ProviderConfigError("config_too_large")
        text = data.decode("utf-8")
        depth = 0
        for count, event in enumerate(yaml.parse(text, Loader=StrictLoader), start=1):
            if count > 2048 or isinstance(event, AliasEvent) or getattr(event, "anchor", None):
                raise ProviderConfigError("yaml_complexity_rejected")
            if getattr(event, "tag", None):
                raise ProviderConfigError("yaml_tags_rejected")
            if isinstance(event, (MappingStartEvent, SequenceStartEvent)):
                depth += 1
                if depth > 12:
                    raise ProviderConfigError("yaml_depth_rejected")
            if isinstance(event, (MappingEndEvent, SequenceEndEvent)):
                depth -= 1
        content = yaml.load(text, Loader=StrictLoader)
        config = ProviderConfig.model_validate(content)
        validate_environment(config, environment)
        return config
    except ProviderConfigError:
        raise
    except (OSError, ValueError, TypeError, yaml.YAMLError, RecursionError):
        raise ProviderConfigError("invalid_provider_configuration") from None


def fingerprint(config: ProviderConfig) -> str:
    canonical = json.dumps(
        config.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def snapshot(config: ProviderConfig) -> ConfigSnapshot:
    return ConfigSnapshot(config_hash=fingerprint(config), content=config)


def restore_snapshot(payload: Mapping) -> ConfigSnapshot:
    try:
        if len(json.dumps(payload, allow_nan=False).encode()) > MAX_BYTES:
            raise ValueError("oversized")
        return ConfigSnapshot.model_validate(payload)
    except (ValueError, TypeError, RecursionError):
        raise ProviderConfigError("invalid_config_snapshot") from None


def resolve_execution(
    captured: ConfigSnapshot,
    capability: Capability,
    current_config: ProviderConfig,
    *,
    environment: str,
    environ: Mapping[str, str] | None = None,
) -> ExecutionRoute:
    """Resolve only implemented offline ASR; real protocol declarations never call a vendor."""
    validate_environment(captured.content, environment)
    validate_environment(current_config, environment)
    if capability not in {"asr", "text", "vision"}:
        raise ProviderConfigError("unknown_capability")
    if captured.config_hash != fingerprint(captured.content):
        raise ProviderConfigError("invalid_config_snapshot")
    if captured.config_hash != fingerprint(current_config):
        raise ProviderConfigError("configuration_changed")
    route = getattr(captured.content.providers, capability)
    if not route.enabled:
        raise ProviderConfigError("provider_unconfigured")
    if route.protocol != "offline_fixture":
        # Future adapter may resolve key_env from environ only after explicit enablement.
        # Never read a real credential while the protocol itself is unsupported.
        raise ProviderConfigError("provider_protocol_unsupported")
    return ExecutionRoute(
        capability=capability, route=route, config_hash=captured.config_hash, synthetic=True
    )
