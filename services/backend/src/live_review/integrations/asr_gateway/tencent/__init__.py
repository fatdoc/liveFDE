from live_review.integrations.asr_gateway.contracts import ASRHealth
from live_review.integrations.asr_gateway.tencent.config import TencentConfig


class TencentASRProvider:
    def __init__(self, config: TencentConfig, *, http_transport=None, ws_connect=None):
        self.config, self.http_transport, self.ws_connect = config, http_transport, ws_connect

    async def transcribe_file(self, path, request):
        from live_review.integrations.asr_gateway.tencent.file import FileRecognizer

        return await FileRecognizer(self.config, self.http_transport).transcribe(path, request)

    def transcribe_stream(self, chunks, request):
        from live_review.integrations.asr_gateway.tencent.realtime import RealtimeRecognizer

        return RealtimeRecognizer(self.config, self.ws_connect).stream(chunks, request)

    async def health(self):
        ready = bool(
            self.config.secret_id.get_secret_value() and self.config.secret_key.get_secret_value()
        )
        capabilities = ["file"]
        if self.config.app_id:
            capabilities.append("stream_v2")
        return ASRHealth(
            provider="tencent",
            ready=ready,
            reason="configuration_only_not_network_verified" if ready else "credentials_missing",
            capabilities=tuple(capabilities),
            network_checked=False,
        )


__all__ = ["TencentASRProvider", "TencentConfig"]
