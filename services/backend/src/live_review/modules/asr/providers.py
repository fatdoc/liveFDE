"""Public configuration capabilities; inspecting these never contacts a provider."""

from live_review.core.provider_config import ProviderConfigError
from live_review.integrations.asr_gateway.contracts import ASRError
from live_review.integrations.asr_gateway.factory import create_provider, registry_for
from live_review.integrations.media import MediaError


def provider_options(settings):
    try:
        registry = registry_for(settings)
    except (ASRError, ProviderConfigError, MediaError):
        registry = None
    options = []
    for name in ("local", "tencent"):
        item = {
            "provider": name,
            "configured": False,
            "reason": "model_configuration_missing",
            "max_duration_seconds": None,
            "max_audio_bytes": 5_000_000 if name == "tencent" else None,
            "network_checked": False,
        }
        if registry is not None:
            limit = min(registry.loaded.public.media.max_duration_seconds, 14400)
            item["max_duration_seconds"] = min(limit, 156) if name == "tencent" else limit
            try:
                # Construction checks configuration/credentials, never health or inference.
                create_provider(registry, name)
                item.update(configured=True, reason="configuration_only_not_network_verified")
            except (ASRError, ProviderConfigError) as error:
                item["reason"] = (
                    error.code
                    if isinstance(error, ASRError)
                    else "model_not_registered"
                    if str(error) == "model_not_registered"
                    else "invalid_model_configuration"
                )
            except ImportError:
                item["reason"] = "provider_dependencies_missing"
        options.append(item)
    return {"providers": options}
