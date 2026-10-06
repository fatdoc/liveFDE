"""One adapter factory for registry execution routes and the explicit legacy bridge."""

from live_review.integrations.asr.compatible import OpenAICompatibleASRProvider
from live_review.integrations.asr.offline import OfflineFixtureProvider
from live_review.integrations.media import MediaError


def create_asr_adapter(execution, *, media, fixture_payload=None, environment, allow_network=False):
    if execution.capability != "asr":
        raise MediaError("model_capability_mismatch")
    route = execution.route
    if execution.synthetic:
        if route.protocol != "offline_fixture":
            raise MediaError("provider_protocol_mismatch")
        return OfflineFixtureProvider(fixture_payload, enabled=True, environment=environment)
    if fixture_payload is not None:
        raise MediaError("fixture_with_real_provider")
    if route.protocol != "openai_compatible" or route.operation != "audio_transcriptions":
        raise MediaError("provider_protocol_unsupported")
    return OpenAICompatibleASRProvider(
        provider=route.provider,
        model=route.model,
        base_url=route.base_url,
        api_key=execution.api_key,
        timeout_seconds=route.timeout_seconds,
        max_requests=route.max_requests,
        max_audio_duration_seconds=media.max_duration_seconds,
        allow_network=allow_network is True,
        environment=environment,
    )
