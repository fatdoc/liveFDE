"""Layered public policy; secrets stay private and never mutate the process environment."""

import copy
import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import Field, SecretStr

from live_review.core.model_config.models import FieldSource, PublicModelConfig
from live_review.core.model_config.safe_io import read_dotenv, read_yaml
from live_review.core.provider_config import FrozenModel, ProviderConfigError

ENVIRONMENTS = {
    "dev": "development",
    "development": "development",
    "test": "test",
    "staging": "staging",
    "prod": "production",
    "production": "production",
}
ENV_FIELDS = {
    "LIVE_MODEL_ASR_DEFAULT": ("aliases", "asr.default"),
    "LIVE_MODEL_LLM_DEFAULT": ("aliases", "llm.default"),
    "LIVE_MODEL_SEGMENT_SECONDS": ("media", "segment_seconds"),
    "LIVE_MODEL_MAX_DURATION_SECONDS": ("media", "max_duration_seconds"),
}
DEFAULTS = {
    "schema_version": 2,
    "revision": "registry-v2",
    "media": {},
    "models": {
        "asr_unconfigured": {"capability": "asr", "route": {}},
        "llm_unconfigured": {"capability": "llm", "route": {}},
    },
    "aliases": {"asr.default": "asr_unconfigured", "llm.default": "llm_unconfigured"},
}


class LoadedModelConfig(FrozenModel):
    public: PublicModelConfig
    provenance: tuple[FieldSource, ...]
    config_dir: str
    local_path: str | None
    dotenv_path: str | None
    credential_values: tuple[tuple[str, SecretStr], ...] = Field(exclude=True, repr=False)

    def source_locator(self):
        return {
            "config_dir": self.config_dir,
            "environment": self.public.environment,
            "local_path": self.local_path,
            "dotenv_path": self.dotenv_path,
        }

    def credential(self, name):
        return next(
            (value.get_secret_value() for key, value in self.credential_values if key == name), None
        )


def deep_merge(base: dict, overlay: dict) -> dict:
    """Maps recurse, lists/scalars replace; null is literal replacement (not deletion)."""
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def trace_fields(data, source, trace, prefix=""):
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            trace_fields(value, source, trace, path)
        else:
            # Replaced subtree cannot retain stale provenance descendants.
            for old in list(trace):
                if old.startswith(path + "."):
                    del trace[old]
            trace[path] = source


def load_model_config(
    config_dir: Path,
    *,
    environment: str,
    local_path: Path | None = None,
    dotenv_path: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> LoadedModelConfig:
    try:
        canonical_env = ENVIRONMENTS.get(environment)
        if canonical_env is None:
            raise ProviderConfigError("invalid_environment")
        config_dir = Path(config_dir)
        if (
            not config_dir.is_absolute()
            or config_dir.resolve() != config_dir
            or not config_dir.is_dir()
        ):
            raise ProviderConfigError("invalid_config_directory")
        protected = canonical_env in {"staging", "production"}
        if protected and local_path is not None:
            raise ProviderConfigError("local_overlay_forbidden")
        local = None if protected else (local_path or config_dir / "local.yaml")
        dotenv = dotenv_path if dotenv_path else (None if protected else config_dir.parent / ".env")
        system = os.environ if environ is None else environ
        private_values = (
            read_dotenv(Path(dotenv))
            if dotenv and (Path(dotenv).exists() or Path(dotenv).is_symlink())
            else {}
        )
        if dotenv_path and not Path(dotenv_path).exists():
            raise ProviderConfigError("private_environment_missing")
        # System values win; only named key_env references will be kept privately below.
        combined = private_values | dict(system)
        merged, trace = copy.deepcopy(DEFAULTS), {}
        trace_fields(merged, "builtin", trace)
        layers = [
            (config_dir / "models.yaml", "base"),
            (config_dir / "environments" / f"{canonical_env}.yaml", canonical_env),
        ]
        if local is not None:
            layers.append((Path(local), "local"))
        for path, source in layers:
            if path.exists() or path.is_symlink():
                layer = read_yaml(path)
                merged = deep_merge(merged, layer)
                trace_fields(layer, source, trace)
            elif source == "local" and local_path is not None:
                raise ProviderConfigError("local_overlay_missing")
        for name, (section, field) in ENV_FIELDS.items():
            if name in combined:
                raw = combined[name]
                if section == "media":
                    if not isinstance(raw, str) or not raw.isdigit():
                        raise ProviderConfigError("invalid_environment_override")
                    raw = int(raw)
                merged = deep_merge(merged, {section: {field: raw}})
                trace[f"{section}.{field}"] = "environment" if name in system else "dotenv"
        if "environment" in merged:
            raise ProviderConfigError("environment_must_be_server_selected")
        data = copy.deepcopy(merged)
        data["environment"] = canonical_env
        data["models"] = tuple(
            {"name": name, **value} for name, value in sorted(data["models"].items())
        )
        data["aliases"] = tuple(
            {"name": name, "model": value} for name, value in sorted(data["aliases"].items())
        )
        public = PublicModelConfig.model_validate(data)
        refs = {model.route.key_env for model in public.models if model.route.key_env}
        secrets = tuple(
            (name, SecretStr(combined[name])) for name in sorted(refs) if name in combined
        )
        return LoadedModelConfig(
            public=public,
            provenance=tuple(FieldSource(field_path=k, source=v) for k, v in sorted(trace.items())),
            config_dir=str(config_dir),
            local_path=str(local) if local is not None and Path(local).exists() else None,
            dotenv_path=str(dotenv) if dotenv is not None and Path(dotenv).exists() else None,
            credential_values=secrets,
        )
    except ProviderConfigError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ProviderConfigError("invalid_model_configuration") from None
