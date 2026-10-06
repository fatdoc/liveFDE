"""Unified gateway policy. A durable recorder is mandatory before any cloud call."""

from contextlib import aclosing

from live_review.integrations.asr_gateway.contracts import ASRError
from live_review.integrations.asr_gateway.factory import create_provider

FALLBACK_ERRORS = frozenset(
    {
        "local_model_busy",
        "local_inference_failed",
        "local_device_out_of_memory",
        "local_timeout",
        "worker_unavailable",
        "worker_busy",
        "worker_timeout",
    }
)


class ASRGateway:
    def __init__(self, registry, preferences, grant, recorder=None):
        self.registry, self.preferences, self.grant = registry, preferences, grant
        self.recorder = recorder

    def cloud_allowed(self):
        return (
            self.preferences.privacy == "cloud_allowed"
            and self.grant.get("allow_network") is True
            and (self.grant.get("max_requests") or 0) >= 1
            and (self.grant.get("max_cost_usd") or 0) > 0
        )

    def provider(self, name):
        if name == "tencent" and not self.cloud_allowed():
            raise ASRError("cloud_authorization_required")
        return create_provider(self.registry, name)

    async def transcribe_file(self, path, request):
        selected = self.preferences.provider
        if selected == "local":
            try:
                provider = self.provider("local")
                return await provider.transcribe_file(
                    path,
                    request.model_copy(
                        update={
                            "allow_network": False,
                            "privacy": "local_only",
                        }
                    ),
                )
            except ASRError as error:
                if (
                    error.unknown
                    or error.code not in FALLBACK_ERRORS
                    or not self.preferences.allow_cloud_fallback
                    or not self.cloud_allowed()
                ):
                    raise
                selected = "tencent"
        if selected != "tencent" or self.recorder is None:
            raise ASRError("durable_cloud_recorder_required")
        provider = self.provider("tencent")
        # Recorder enters a committed intent BEFORE constructing/sending a billable request.
        return await self.recorder.file(
            provider,
            path,
            request.model_copy(
                update={
                    "allow_network": True,
                    "privacy": "cloud_allowed",
                }
            ),
        )

    async def transcribe_stream(self, chunks, request):
        # Consumed samples and interim speaker state cannot be replayed across providers.
        provider = self.provider(self.preferences.provider)
        if self.preferences.provider == "tencent":
            if self.recorder is None:
                raise ASRError("durable_cloud_recorder_required")
            async with aclosing(self.recorder.stream(provider, chunks, request)) as events:
                async for event in events:
                    yield event
        else:
            events = provider.transcribe_stream(
                chunks,
                request.model_copy(
                    update={
                        "allow_network": False,
                        "privacy": "local_only",
                    }
                ),
            )
            async with aclosing(events):
                async for event in events:
                    yield event

    async def health(self):
        # Configuration/resource inspection only, not connectivity or inference.
        return await create_provider(self.registry, self.preferences.provider).health()
