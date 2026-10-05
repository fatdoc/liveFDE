"""Audio-transcription protocol only; no assumption that a chat vendor supports it."""

import json
import math
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr

from live_review.integrations.asr.models import LocalUtterance, SegmentTranscript
from live_review.integrations.media.process import MediaError, check_cancel


class ASRUnknownCall(MediaError):
    def __init__(self):
        super().__init__("call_result_unknown")


class OpenAICompatibleASRProvider:
    synthetic = False

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        base_url: str,
        api_key: SecretStr,
        timeout_seconds: float,
        max_requests: int,
        max_audio_duration_seconds: int,
        allow_network: bool = False,
        environment: str = "development",
        transport: httpx.MockTransport | None = None,
    ):
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise MediaError("invalid_asr_base_url")
        testing = isinstance(transport, httpx.MockTransport) and environment == "test"
        if not allow_network and not testing:
            raise MediaError("asr_network_not_authorized")
        if transport is not None and not testing:
            raise MediaError("asr_transport_not_allowed")
        if parsed.scheme != "https" and not testing:
            raise MediaError("asr_https_required")
        if not model or not provider or not api_key.get_secret_value():
            raise MediaError("asr_config_incomplete")
        if not 0 < timeout_seconds <= 600 or not 1 <= max_requests <= 10000:
            raise MediaError("invalid_asr_limits")
        if not 1 <= max_audio_duration_seconds <= 86400:
            raise MediaError("invalid_asr_limits")
        self.provider, self.model = provider, model
        self._key = api_key
        self._url = base_url.rstrip("/") + "/audio/transcriptions"
        self._timeout, self._transport = timeout_seconds, transport
        self._max_requests, self._max_samples = max_requests, max_audio_duration_seconds * 16000
        self._requests, self._samples = 0, 0

    def preflight(self, segments):
        if self._requests + len(segments) > self._max_requests:
            raise MediaError("asr_request_budget_exceeded")
        if self._samples + sum(s.end_sample - s.start_sample for s in segments) > self._max_samples:
            raise MediaError("asr_duration_budget_exceeded")

    def transcribe_segment(self, segment, audio_path: Path, *, cancel=None):
        check_cancel(cancel)
        self.preflight((segment,))
        self._requests += 1
        self._samples += segment.end_sample - segment.start_sample
        try:
            with (
                httpx.Client(
                    timeout=self._timeout,
                    follow_redirects=False,
                    trust_env=False,
                    transport=self._transport,
                ) as client,
                audio_path.open("rb") as audio,
            ):
                with client.stream(
                    "POST",
                    self._url,
                    headers={"Authorization": f"Bearer {self._key.get_secret_value()}"},
                    data={
                        "model": self.model,
                        "response_format": "verbose_json",
                        "timestamp_granularities[]": "segment",
                    },
                    files={"file": ("audio.wav", audio, "audio/wav")},
                ) as response:
                    if 300 <= response.status_code < 400:
                        raise MediaError("asr_redirect_rejected")
                    if response.status_code >= 500:
                        raise ASRUnknownCall
                    if response.status_code >= 400:
                        raise MediaError("asr_http_rejected")
                    if not 200 <= response.status_code < 300:
                        raise ASRUnknownCall
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        # Once sent, cancellation cannot establish provider outcome.
                        if cancel and cancel():
                            raise ASRUnknownCall
                        content.extend(chunk)
                        if len(content) > 1024 * 1024:
                            raise ASRUnknownCall
        except httpx.HTTPError as error:
            raise ASRUnknownCall from error
        try:
            payload = json.loads(content)
            return self._parse(payload)
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            raise ASRUnknownCall from error

    @staticmethod
    def _parse(payload):
        segments = payload.get("segments")
        if not isinstance(segments, list) or not segments:
            # Text-only responses cannot invent timestamped completeness.
            return SegmentTranscript(coverage="unknown", missing_words=True)
        if len(segments) > 2000:
            raise ValueError("Response size")
        utterances = []
        for segment in segments:

            def timestamp(value):
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                ):
                    return None
                return round(value * 1000)

            utterances.append(
                LocalUtterance(
                    text=segment["text"],
                    start_ms=timestamp(segment.get("start")),
                    end_ms=timestamp(segment.get("end")),
                )
            )

        # Full text omitted from segments means words may be missing. Whitespace
        # differences are formatting; other content differences are not discarded.
        def normalized(text):
            return "".join(text.split())

        missing = not isinstance(payload.get("text"), str) or normalized(
            payload["text"]
        ) != normalized("".join(u.text for u in utterances))
        return SegmentTranscript(
            utterances=tuple(utterances), coverage="full", missing_words=missing
        )
