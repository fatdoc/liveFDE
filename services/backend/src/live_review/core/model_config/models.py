"""Immutable public registry contracts; mutable YAML maps are normalized into tuples."""

from ipaddress import ip_address, ip_network
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from live_review.core.model_config.asr_routes import LocalASRRoute, TencentASRRoute
from live_review.core.provider_config import FrozenModel, MediaConfig, ProviderRoute

Capability = Literal["asr", "llm", "vision", "embedding", "reranker", "detection"]


class ModelParameters(FrozenModel):
    temperature: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)
    device: str | None = Field(default=None, pattern=r"^(cpu|mps|cuda(:[0-9]{1,2})?)$")
    model_path: str | None = Field(default=None, min_length=1, max_length=512)
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)

    @field_validator("model_path")
    @classmethod
    def local_path_declaration(cls, value):
        if value is not None and (
            any(c in value for c in ("$", "~", "\\"))
            or "://" in value
            or ".." in value.split("/")
            or any(ord(c) < 32 for c in value)
        ):
            raise ValueError("invalid_model_path")
        return value


def private_endpoint(host):
    """Declaration-only allowlist; never resolve DNS or connect to validate a host."""
    if host == "localhost":
        return True
    try:
        address = ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or any(
        address in ip_network(network)
        for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
    )


class DeclaredRoute(FrozenModel):
    """Non-executable model descriptions; no downloads, discovery or adapter defaults."""

    protocol: Literal["huggingface", "ollama", "yolo"]
    enabled: bool = False
    timeout_seconds: int = Field(default=60, ge=1, le=600)
    provider: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    model: str = Field(min_length=1, max_length=128)
    base_url: str | None = Field(default=None, max_length=512)
    key_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,127}$")

    @field_validator("model")
    @classmethod
    def model_name(cls, value):
        return ProviderRoute.safe_model(value)

    @model_validator(mode="after")
    def local_declaration(self):
        if self.protocol != "ollama":
            if self.base_url is not None:
                raise ValueError("local_model_does_not_use_base_url")
            return self
        if self.base_url is None:
            raise ValueError("ollama_endpoint_required")
        parsed = urlsplit(self.base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or any(c.isspace() for c in self.base_url)
            or any(c in self.base_url for c in ("$", "%", "\\"))
            or ".." in parsed.path.split("/")
        ):
            raise ValueError("invalid_declared_endpoint")
        if parsed.scheme == "http" and not private_endpoint(parsed.hostname):
            raise ValueError("plaintext_endpoint_must_be_private")
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError("invalid_port")
        return self


class ModelDescriptor(FrozenModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")
    capability: Capability
    route: ProviderRoute | DeclaredRoute | LocalASRRoute | TencentASRRoute
    parameters: ModelParameters = Field(default_factory=ModelParameters)

    @model_validator(mode="after")
    def protocol_matches_capability(self):
        if isinstance(self.route, (LocalASRRoute, TencentASRRoute)) and self.capability != "asr":
            raise ValueError("gateway_route_requires_asr")
        if isinstance(self.route, DeclaredRoute):
            allowed = {
                "huggingface": {"llm", "embedding", "reranker", "vision"},
                "ollama": {"llm", "embedding"},
                "yolo": {"vision", "detection"},
            }
            if self.capability not in allowed[self.route.protocol]:
                raise ValueError("declared_protocol_capability_mismatch")
        if self.capability == "asr" and any(
            v is not None for v in self.parameters.model_dump().values()
        ):
            raise ValueError("asr_parameters_not_implemented")
        if self.parameters.temperature is not None and self.capability != "llm":
            raise ValueError("temperature_requires_llm")
        if self.parameters.confidence is not None and self.capability not in {
            "vision",
            "detection",
        }:
            raise ValueError("confidence_requires_vision_or_detection")
        if self.route.protocol == "offline_fixture" and self.capability != "asr":
            raise ValueError("fixture_requires_asr")
        if self.route.protocol == "openai_compatible" and self.capability == "asr":
            if self.route.operation != "audio_transcriptions":
                raise ValueError("asr_operation_required")
        if self.capability != "asr" and getattr(self.route, "operation", None) is not None:
            raise ValueError("audio_operation_requires_asr")
        return self


class ModelAlias(FrozenModel):
    name: str = Field(
        pattern=r"^(asr|llm|vision|embedding|reranker|detection)\.[a-z][a-z0-9_.-]{0,63}$"
    )
    model: str


class PublicModelConfig(FrozenModel):
    schema_version: Literal[2] = 2
    revision: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")
    environment: Literal["development", "test", "staging", "production"]
    media: MediaConfig = Field(default_factory=MediaConfig)
    models: tuple[ModelDescriptor, ...] = Field(min_length=1, max_length=64)
    aliases: tuple[ModelAlias, ...] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def valid_references(self):
        names = {model.name: model for model in self.models}
        if len(names) != len(self.models) or len({a.name for a in self.aliases}) != len(
            self.aliases
        ):
            raise ValueError("duplicate_model_or_alias")
        for alias in self.aliases:
            model = names.get(alias.model)
            if model is None or model.capability != alias.name.split(".", 1)[0]:
                raise ValueError("invalid_model_reference")
        if self.environment in {"staging", "production"} and any(
            model.route.protocol == "offline_fixture" for model in self.models
        ):
            raise ValueError("synthetic_forbidden")
        return self


class FieldSource(FrozenModel):
    field_path: str
    source: str
