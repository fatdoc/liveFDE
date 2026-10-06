"""Explicit v1 bridge and v2 registry snapshots; never silently migrate stored jobs."""

from pathlib import Path

from live_review.core.provider_config import (
    load_config,
    resolve_execution,
    restore_snapshot,
    snapshot,
)
from live_review.integrations.media import MediaError

ENVIRONMENTS = {"development", "test", "staging", "production"}


def config_environment(settings, requested=None):
    runtime = settings.environment
    if runtime not in {"development", "production"}:
        raise MediaError("runtime_environment_invalid")
    selected = requested or runtime
    if selected not in ENVIRONMENTS:
        raise MediaError("configuration_environment_invalid")
    if runtime == "development" and selected not in {"development", "test"}:
        raise MediaError("configuration_environment_runtime_mismatch")
    if runtime == "production" and selected not in {"production", "staging"}:
        raise MediaError("configuration_environment_downgrade")
    return selected


def policy_environment(environment):
    return "production" if environment == "staging" else environment


def prepare_configuration(
    settings,
    *,
    config_path=None,
    config_dir=None,
    model_id=None,
    config_env=None,
    local_path=None,
    dotenv_path=None,
    allow_network=False,
):
    if (config_path is None) == (config_dir is None):
        raise MediaError("configuration_source_required")
    if config_path is not None:
        if any(value is not None for value in (model_id, config_env, local_path, dotenv_path)):
            raise MediaError("legacy_configuration_options_invalid")
        # Keep the original v1 load/snapshot semantics for existing single YAML callers.
        current = load_config(config_path, environment=settings.environment)
        captured = snapshot(current)
        execution = resolve_execution(
            captured,
            "asr",
            current,
            environment=settings.environment,
            allow_network=allow_network is True,
        )
        return captured, execution, {"provider_config_path": str(config_path)}

    from live_review.core.model_config import load_model_config
    from live_review.core.model_registry import ModelRegistry

    environment = config_environment(settings, config_env)
    loaded = load_model_config(
        Path(config_dir), environment=environment, local_path=local_path, dotenv_path=dotenv_path
    )
    registry = ModelRegistry(loaded)
    selected = model_id or "asr.default"
    descriptor = registry.get(selected)
    if descriptor.capability != "asr":
        raise MediaError("model_capability_mismatch")
    captured = registry.snapshot()
    execution = registry.resolve(selected, allow_network=allow_network is True, captured=captured)
    return (
        captured,
        execution,
        {
            "provider_config_locator": loaded.source_locator(),
            "model_id": selected,
            "runtime_environment": settings.environment,
            "provider_config_options": {
                "local_explicit": local_path is not None,
                "dotenv_explicit": dotenv_path is not None,
            },
        },
    )


def restore_configuration(data, settings):
    payload = data["provider_snapshot"]
    if payload.get("snapshot_version") == 1:
        captured = restore_snapshot(payload)
        current = load_config(Path(data["provider_config_path"]), environment=settings.environment)
        execution = resolve_execution(
            captured,
            "asr",
            current,
            environment=settings.environment,
            allow_network=data.get("allow_network") is True,
        )
        return captured, execution
    if payload.get("snapshot_version") != 2:
        raise MediaError("configuration_snapshot_version_unsupported")

    from live_review.core.model_config import load_model_config
    from live_review.core.model_registry import ModelRegistry
    from live_review.core.model_registry import restore_snapshot as restore_registry_snapshot

    if data.get("runtime_environment") != settings.environment:
        raise MediaError("runtime_environment_changed")
    locator = data["provider_config_locator"]
    environment = config_environment(settings, locator["environment"])
    options = data["provider_config_options"]
    loaded = load_model_config(
        Path(locator["config_dir"]),
        environment=environment,
        local_path=Path(locator["local_path"]) if options["local_explicit"] else None,
        dotenv_path=Path(locator["dotenv_path"]) if options["dotenv_explicit"] else None,
    )
    if loaded.source_locator() != locator:
        raise MediaError("configuration_locator_changed")
    registry = ModelRegistry(loaded)
    captured = restore_registry_snapshot(payload)
    selected = data["model_id"]
    if registry.get(selected).capability != "asr":
        raise MediaError("model_capability_mismatch")
    execution = registry.resolve(
        selected, allow_network=data.get("allow_network") is True, captured=captured
    )
    return captured, execution


def execution_environment(data, settings):
    if data["provider_snapshot"].get("snapshot_version") == 1:
        return settings.environment
    selected = config_environment(settings, data["provider_config_locator"]["environment"])
    return policy_environment(selected)
