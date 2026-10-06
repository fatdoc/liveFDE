"""Immutable public registry contracts; mutable YAML maps are normalized into tuples."""

from typing import Literal

from pydantic import Field, field_validator, model_validator

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


class ModelDescriptor(FrozenModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")
    capability: Capability
    route: ProviderRoute
    parameters: ModelParameters = Field(default_factory=ModelParameters)

    @model_validator(mode="after")
    def protocol_matches_capability(self):
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
        if self.capability != "asr" and self.route.operation is not None:
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
