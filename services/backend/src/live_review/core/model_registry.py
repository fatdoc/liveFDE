"""Named model descriptions and v2 retry integrity; legacy v1 remains untouched."""

import hashlib
import json
from collections.abc import Mapping
from typing import Literal

from pydantic import Field, model_validator

from live_review.core.model_config import LoadedModelConfig
from live_review.core.model_config.models import PublicModelConfig
from live_review.core.provider_config import (
    FrozenModel,
    ProviderConfig,
    ProviderConfigError,
    Providers,
    resolve_execution,
)
from live_review.core.provider_config import (
    snapshot as legacy_snapshot,
)


def fingerprint(content: PublicModelConfig):
    value = json.dumps(
        content.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(value.encode()).hexdigest()


class ModelSnapshot(FrozenModel):
    snapshot_version: Literal[2] = 2
    content: PublicModelConfig
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def integrity(self):
        if fingerprint(self.content) != self.config_hash:
            raise ValueError("snapshot_fingerprint_mismatch")
        return self


def restore_snapshot(payload: Mapping) -> ModelSnapshot:
    try:
        encoded = json.dumps(payload, allow_nan=False)
        if len(encoded.encode()) > 262144:
            raise ValueError("oversized")
        return ModelSnapshot.model_validate_json(encoded)
    except (ValueError, TypeError, RecursionError):
        raise ProviderConfigError("invalid_model_snapshot") from None


class ModelRegistry:
    def __init__(self, loaded: LoadedModelConfig):
        self.loaded = loaded

    def get(self, name: str):
        target = next(
            (alias.model for alias in self.loaded.public.aliases if alias.name == name), name
        )
        model = next((item for item in self.loaded.public.models if item.name == target), None)
        if model is None:
            raise ProviderConfigError("model_not_registered")
        return model

    def validate_references(self, names, expected_capability):
        if expected_capability not in {
            "asr",
            "llm",
            "vision",
            "embedding",
            "reranker",
            "detection",
        }:
            raise ProviderConfigError("invalid_capability")
        result = tuple(self.get(name) for name in names)
        if any(model.capability != expected_capability for model in result):
            raise ProviderConfigError("model_capability_mismatch")
        return result

    def snapshot(self):
        return ModelSnapshot(
            content=self.loaded.public, config_hash=fingerprint(self.loaded.public)
        )

    def resolve(self, name: str, *, allow_network=False, captured: ModelSnapshot | None = None):
        current = self.snapshot()
        if captured is not None:
            # Revalidate copies too, including model_copy bypasses of frozen validators.
            restored = restore_snapshot(captured.model_dump(mode="json"))
            if restored.config_hash != current.config_hash:
                raise ProviderConfigError("configuration_changed")
        model = self.get(name)
        if model.capability != "asr":
            raise ProviderConfigError("model_capability_not_executable")
        if model.route.protocol in {"local_funasr", "tencent_asr"}:
            raise ProviderConfigError("gateway_execution_required")
        legacy = ProviderConfig(
            revision=self.loaded.public.revision,
            media=self.loaded.public.media,
            providers=Providers(asr=model.route),
        )
        loaded = self.loaded

        class Credentials:
            def get(self, key):
                return loaded.credential(key)

        result = resolve_execution(
            legacy_snapshot(legacy),
            "asr",
            legacy,
            environment="production"
            if self.loaded.public.environment in {"staging", "production"}
            else self.loaded.public.environment,
            allow_network=allow_network,
            environ=Credentials(),
        )
        return result.model_copy(update={"config_hash": current.config_hash})
