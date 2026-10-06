"""Apply a workspace LLM view to the existing immutable Loader result."""

from pydantic import SecretStr

from live_review.core.model_config import LoadedModelConfig, load_model_config
from live_review.core.model_config.llm_routes import LLMDebugRoute
from live_review.core.model_config.models import (
    FieldSource,
    ModelAlias,
    ModelDescriptor,
    PublicModelConfig,
)
from live_review.core.provider_config import ProviderConfigError, ProviderRoute
from live_review.workers.media_configuration import config_environment


def effective_llm(settings, value, api_key):
    if settings.model_config_dir is None:
        raise ProviderConfigError("invalid_config_directory")
    environment = config_environment(settings, settings.model_config_environment)
    loaded = load_model_config(
        settings.model_config_dir, environment=environment, dotenv_path=settings.model_dotenv_path
    )
    route_data = dict(
        base_url=value.base_url,
        model=value.model,
        timeout_seconds=value.timeout_seconds,
        key_env="LIVE_WORKSPACE_LLM_KEY",
    )
    if value.base_url.startswith("http://"):
        if settings.environment != "development" or environment not in {"development", "test"}:
            raise ProviderConfigError("llm_http_not_allowed")
        route = LLMDebugRoute(**route_data)
    else:
        route = ProviderRoute(
            protocol="openai_compatible",
            enabled=False,
            provider="workspace_llm",
            max_requests=1,
            max_cost_usd=1,
            **route_data,
        )
    model = ModelDescriptor(name="workspace_llm", capability="llm", route=route)
    content = loaded.public.model_dump(mode="python")
    content["models"] = tuple(m for m in loaded.public.models if m.name != model.name) + (model,)
    content["aliases"] = tuple(a for a in loaded.public.aliases if a.name != "llm.default") + (
        ModelAlias(name="llm.default", model=model.name),
    )
    content["revision"] = "workspace-" + value.revision
    public = PublicModelConfig.model_validate(content)
    return LoadedModelConfig(
        public=public,
        provenance=loaded.provenance
        + (FieldSource(field_path="models.workspace_llm", source="workspace"),),
        config_dir=loaded.config_dir,
        local_path=loaded.local_path,
        dotenv_path=loaded.dotenv_path,
        credential_values=tuple(
            (k, v) for k, v in loaded.credential_values if k != "LIVE_WORKSPACE_LLM_KEY"
        )
        + (("LIVE_WORKSPACE_LLM_KEY", SecretStr(api_key)),),
    )
