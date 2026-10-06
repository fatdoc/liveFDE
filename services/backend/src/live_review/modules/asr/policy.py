"""Workspace defaults layered beside model YAML, versioned separately from v2 snapshots."""

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from live_review.core.model_config import deep_merge
from live_review.core.model_config.safe_io import read_yaml
from live_review.core.provider_config import ProviderConfigError
from live_review.modules.asr.schemas import Preferences
from live_review.workers.media_configuration import config_environment


class GatewayPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: int = Field(default=1, ge=1, le=1)
    defaults: Preferences = Field(default_factory=Preferences)


def load_policy(settings):
    if settings is None or settings.model_config_dir is None:
        return GatewayPolicy()
    directory = settings.model_config_dir
    environment = config_environment(settings, settings.model_config_environment)
    merged = {}
    paths = [directory / "asr-policy.yaml", directory / "environments" / f"{environment}.asr.yaml"]
    if environment in {"development", "test"}:
        paths.append(directory / "asr.local.yaml")
    for path in paths:
        if path.exists() or path.is_symlink():
            merged = deep_merge(merged, read_yaml(path))
    try:
        return GatewayPolicy.model_validate(merged)
    except ValidationError:
        raise ProviderConfigError("invalid_asr_policy") from None


def policy_snapshot(settings):
    content = load_policy(settings).model_dump(mode="json")
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return {"content": content, "sha256": hashlib.sha256(canonical.encode()).hexdigest()}
