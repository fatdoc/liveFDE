"""Disabled Registry descriptor only; no credentials or executable vision adapter.

HTTP debug endpoints are not registered: LLMDebugRoute is exclusively text.
The default endpoint is resolved from current LLM metadata on every invocation.
"""

from live_review.core.model_config import load_model_config
from live_review.core.model_config.models import FieldSource, ModelAlias, ModelDescriptor
from live_review.core.provider_config import ProviderConfigError, ProviderRoute
from live_review.integrations.llm.connection import CheckFailure, validate_target
from live_review.modules.llm.vision_store import Store
from live_review.workers.media_configuration import config_environment


def effective_vision(settings, workspace_id, loaded=None):
    environment = config_environment(settings, settings.model_config_environment)
    if loaded is None:
        if settings.model_config_dir is None:
            raise ProviderConfigError("invalid_config_directory")
        loaded = load_model_config(
            settings.model_config_dir,
            environment=environment,
            dotenv_path=settings.model_dotenv_path,
        )
    # A caller may pass a previously overlaid registry; removing our stale declaration
    # ensures disabling a workspace preference cannot leave that route visible.
    if any(m.name == "workspace_vision" for m in loaded.public.models):
        content = loaded.public.model_dump(mode="python")
        content["models"] = tuple(m for m in loaded.public.models if m.name != "workspace_vision")
        content["aliases"] = tuple(
            a for a in loaded.public.aliases if a.model != "workspace_vision"
        )
        loaded = loaded.model_copy(update={"public": type(loaded.public).model_validate(content)})
    value = Store(settings, workspace_id).read()
    # Neither disabled preferences, incomplete configuration nor HTTP debug settings
    # grant a usable registry route. No secrets are read or copied for declarations.
    if not value.enabled or not value.configured or value.debug_http:
        return loaded
    try:
        validate_target(settings, environment, value.effective_base_url)
    except CheckFailure:
        raise ProviderConfigError("vision_endpoint_rejected") from None
    descriptor = ModelDescriptor(
        name="workspace_vision",
        capability="vision",
        route=ProviderRoute(
            protocol="openai_compatible",
            enabled=False,
            provider="workspace_vision",
            base_url=value.effective_base_url,
            model=value.model,
            timeout_seconds=value.timeout_seconds,
            key_env="LIVE_WORKSPACE_VISION_KEY",
            max_requests=1,
            max_cost_usd=1,
        ),
    )
    content = loaded.public.model_dump(mode="python")
    content["models"] = tuple(m for m in loaded.public.models if m.name != descriptor.name) + (
        descriptor,
    )
    content["aliases"] = tuple(a for a in loaded.public.aliases if a.name != "vision.default") + (
        ModelAlias(name="vision.default", model=descriptor.name),
    )
    content["revision"] = "vision-" + value.revision
    return loaded.model_copy(
        update={
            "public": type(loaded.public).model_validate(content),
            "provenance": loaded.provenance
            + (FieldSource(field_path="models.workspace_vision", source="workspace"),),
        }
    )
