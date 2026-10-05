import json

import httpx
import pytest
from pydantic import SecretStr
from test_media import media_source as media_source

from live_review.integrations.asr import (
    ASRUnknownCall,
    OfflineFixtureProvider,
    OpenAICompatibleASRProvider,
    transcribe,
)
from live_review.integrations.media import MediaError, extract_audio


@pytest.fixture
def extracted(media_source):
    root, source, output = media_source
    return extract_audio(source, input_root=root, output_root=output, segment_seconds=1), output


def fixture_payload(extraction):
    return {
        "segments": {
            str(s.index): {
                "coverage": "full",
                "missing_words": False,
                "utterances": [
                    {
                        "text": "合成测试文本，非真实听写",
                        "start_ms": 0,
                        "end_ms": s.end_ms - s.start_ms,
                    }
                ],
            }
            for s in extraction.segments
        }
    }


def test_offline_global_timeline_and_explicit_synthetic(extracted):
    extraction, root = extracted
    provider = OfflineFixtureProvider(fixture_payload(extraction), enabled=True, environment="test")
    result = transcribe(extraction, artifact_root=root, provider=provider)
    assert result.complete and result.synthetic and result.provider == "synthetic"
    assert result.utterances[-1].end_ms == extraction.audio_duration_ms
    assert result.utterances[1].start_ms == 1000
    assert json.loads(result.model_dump_json())["timeline"] == "source_relative"
    with pytest.raises(MediaError, match="offline_fixture_not_allowed"):
        OfflineFixtureProvider(fixture_payload(extraction), enabled=True, environment="production")
    with pytest.raises(MediaError, match="offline_fixture_not_allowed"):
        OfflineFixtureProvider(fixture_payload(extraction), environment="test")


@pytest.mark.parametrize(
    "change,code",
    [
        ({"coverage": "partial"}, "coverage_incomplete"),
        ({"missing_words": True}, "words_missing"),
        ({"utterances": [{"text": "合成", "end_ms": 1}]}, "timestamp_missing"),
        (
            {"utterances": [{"text": "合成", "start_ms": 0, "end_ms": 9999}]},
            "timestamp_out_of_range",
        ),
        ({"utterances": []}, "empty_transcript"),
    ],
)
def test_partial_never_complete(extracted, change, code):
    extraction, root = extracted
    payload = fixture_payload(extraction)
    payload["segments"]["0"].update(change)
    result = transcribe(
        extraction,
        artifact_root=root,
        provider=OfflineFixtureProvider(payload, enabled=True, environment="test"),
    )
    assert not result.complete and result.status == "partial"
    assert result.segments[0].error_code == code


def test_missing_failed_and_invalid_audio_segments(extracted):
    extraction, root = extracted
    payload = fixture_payload(extraction)
    del payload["segments"]["0"]
    payload["segments"]["1"] = {"fail": True}
    (root / extraction.segments[2].artifact.path).write_bytes(b"tampered")
    result = transcribe(
        extraction,
        artifact_root=root,
        provider=OfflineFixtureProvider(payload, enabled=True, environment="test"),
    )
    assert not result.complete
    assert [s.error_code for s in result.segments[:3]] == [
        "segment_missing",
        "provider_segment_failed",
        "artifact_integrity_failed",
    ]
    damaged = extraction.model_copy(update={"segments": extraction.segments[1:]})
    with pytest.raises(MediaError, match="segment_timeline_invalid"):
        transcribe(
            damaged,
            artifact_root=root,
            provider=OfflineFixtureProvider(payload, enabled=True, environment="test"),
        )


def compatible(handler, **overrides):
    args = dict(
        provider="configured-vendor",
        model="configured-model",
        base_url="https://asr.invalid/v1",
        api_key=SecretStr("synthetic-test-token"),
        timeout_seconds=1,
        max_requests=10,
        max_audio_duration_seconds=30,
        environment="test",
        transport=httpx.MockTransport(handler),
    )
    args.update(overrides)
    return OpenAICompatibleASRProvider(**args)


def test_compatible_multipart_contract(extracted):
    extraction, root = extracted
    calls = []

    def handle(request):
        body = request.read()
        calls.append(request)
        assert request.url == "https://asr.invalid/v1/audio/transcriptions"
        assert request.headers["authorization"] == "Bearer synthetic-test-token"
        assert b'name="model"' in body and b"configured-model" in body
        assert b"verbose_json" in body and b"timestamp_granularities[]" in body
        assert b"RIFF" in body and b'filename="audio.wav"' in body
        return httpx.Response(
            200, json={"text": "合成", "segments": [{"text": "合成", "start": 0, "end": 0.001}]}
        )

    result = transcribe(extraction, artifact_root=root, provider=compatible(handle))
    assert result.complete and not result.synthetic
    assert len(calls) == len(extraction.segments)
    assert result.utterances[1].start_ms == 1000


def test_transport_disabled_and_budget_before_requests(extracted):
    extraction, root = extracted
    calls = []
    with pytest.raises(MediaError, match="asr_network_not_authorized"):
        compatible(lambda req: None, transport=None)
    provider = compatible(lambda req: calls.append(req), max_requests=1)
    with pytest.raises(MediaError, match="asr_request_budget_exceeded"):
        transcribe(extraction, artifact_root=root, provider=provider)
    assert not calls


@pytest.mark.parametrize("mode", ["timeout", "server", "badjson", "oversized"])
def test_unknown_result_stops_without_retry_or_next_segment(extracted, mode):
    extraction, root = extracted
    calls = []

    def handle(request):
        calls.append(request)
        if mode == "timeout":
            raise httpx.ReadTimeout("synthetic sensitive-token", request=request)
        if mode == "server":
            return httpx.Response(500, text="synthetic sensitive-token")
        if mode == "badjson":
            return httpx.Response(200, text="invalid")
        return httpx.Response(200, content=b"x" * (1024 * 1024 + 1))

    with pytest.raises(ASRUnknownCall, match="call_result_unknown") as raised:
        transcribe(extraction, artifact_root=root, provider=compatible(handle))
    assert "sensitive-token" not in str(raised.value)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "status,code", [(302, "asr_redirect_rejected"), (401, "asr_http_rejected")]
)
def test_redirect_and_error_body_safe(extracted, status, code):
    extraction, root = extracted
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(
            status, headers={"Location": "https://unwanted.invalid"}, text="sensitive-token"
        )

    result = transcribe(extraction, artifact_root=root, provider=compatible(handle))
    assert result.status == "failed" and not result.complete
    assert all(s.error_code == code for s in result.segments)
    assert "sensitive-token" not in result.model_dump_json()
    assert len(calls) == len(extraction.segments)  # No retry or redirect per segment.


def test_text_only_and_missing_words_not_complete(extracted):
    extraction, root = extracted
    result = transcribe(
        extraction,
        artifact_root=root,
        provider=compatible(lambda _: httpx.Response(200, json={"text": "没有时间戳的合成返回"})),
    )
    assert not result.complete
    result = transcribe(
        extraction,
        artifact_root=root,
        provider=compatible(
            lambda _: httpx.Response(
                200,
                json={"text": "合成缺词", "segments": [{"text": "合成", "start": 0, "end": 0.001}]},
            )
        ),
    )
    assert all(s.error_code == "words_missing" for s in result.segments)


def test_duration_budget_and_cancel_before_transport(extracted):
    extraction, root = extracted
    calls = []
    provider = compatible(lambda request: calls.append(request), max_audio_duration_seconds=1)
    with pytest.raises(MediaError, match="asr_duration_budget_exceeded"):
        transcribe(extraction, artifact_root=root, provider=provider)
    with pytest.raises(MediaError, match="canceled"):
        transcribe(extraction, artifact_root=root, provider=provider, cancel=lambda: True)
    assert not calls


@pytest.mark.parametrize("text", ["   ", "\t\n", "\u3000"])
def test_whitespace_response_cannot_be_complete(extracted, text):
    extraction, root = extracted
    result = transcribe(
        extraction,
        artifact_root=root,
        provider=compatible(
            lambda _: httpx.Response(
                200, json={"text": text, "segments": [{"text": text, "start": 0, "end": 0.001}]}
            )
        ),
    )
    assert not result.complete and result.status == "partial"
    assert not result.utterances
    assert result.unlocated[0].text == text
    assert result.unlocated[0].start_ms is None and result.unlocated[0].end_ms is None
    assert result.segments[0].error_code == "blank_transcript"


@pytest.mark.parametrize("mode", ["missing", "text_only", "out_of_range"])
def test_known_text_preserved_without_fabricated_timestamps(extracted, mode):
    extraction, root = extracted
    text = "  原话必须原样保留，包括空格。 "
    payload = {"text": text}
    if mode != "text_only":
        payload["segments"] = [
            {"text": text, "start": None if mode == "missing" else -1, "end": 0.001}
        ]
    result = transcribe(
        extraction,
        artifact_root=root,
        provider=compatible(lambda _: httpx.Response(200, json=payload)),
    )
    assert not result.complete and not result.utterances
    assert result.unlocated[0].text == text
    assert result.unlocated[0].start_ms is None and result.unlocated[0].end_ms is None
    assert result.segments[0].raw_text == text
    from live_review.integrations.asr import Transcript

    assert Transcript.model_validate(result.model_dump(mode="json")) == result


def test_large_timestamp_unknown_and_traceback_redacted(extracted):
    import traceback

    extraction, root = extracted
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={"text": "known", "segments": [{"text": "known", "start": 1e308, "end": 1e308}]},
        )

    with pytest.raises(ASRUnknownCall) as raised:
        transcribe(extraction, artifact_root=root, provider=compatible(handle))
    assert len(calls) == 1
    assert raised.value.__cause__ is None and raised.value.__suppress_context__

    def secret_error(request):
        raise httpx.ReadTimeout("private-synthetic-secret", request=request)

    with pytest.raises(ASRUnknownCall) as raised:
        transcribe(extraction, artifact_root=root, provider=compatible(secret_error))
    assert "private-synthetic-secret" not in "".join(traceback.format_exception(raised.value))


def test_audio_file_cap_before_transport(extracted, tmp_path):
    extraction, root = extracted
    calls = []
    provider = compatible(lambda request: calls.append(request))
    large = tmp_path / "oversize.wav"
    with large.open("wb") as stream:
        stream.truncate(25_000_001)
    with pytest.raises(MediaError, match="asr_audio_size_limit"):
        provider.transcribe_segment(extraction.segments[0], large)
    oversized = extraction.segments[0].model_copy(
        update={
            "artifact": extraction.segments[0].artifact.model_copy(
                update={"size_bytes": 25_000_001}
            )
        }
    )
    with pytest.raises(MediaError, match="asr_audio_size_limit"):
        provider.preflight((oversized,))
    assert not calls


def test_slow_stream_total_deadline_unknown(extracted):
    import time

    extraction, root = extracted
    calls, chunks = [], []

    class SlowStream(httpx.SyncByteStream):
        def __iter__(self):
            for _ in range(20):
                time.sleep(0.025)
                chunks.append(1)
                yield b" "

    def handle(request):
        calls.append(request)
        return httpx.Response(200, stream=SlowStream())

    with pytest.raises(ASRUnknownCall):
        transcribe(
            extraction, artifact_root=root, provider=compatible(handle, timeout_seconds=0.06)
        )
    assert len(calls) == 1 and len(chunks) < 20


def test_explicit_no_speech_is_required_for_empty_complete(extracted):
    extraction, root = extracted
    payload = {
        "segments": {
            str(s.index): {
                "coverage": "full",
                "missing_words": False,
                "no_speech": True,
                "utterances": [],
            }
            for s in extraction.segments
        }
    }
    result = transcribe(
        extraction,
        artifact_root=root,
        provider=OfflineFixtureProvider(payload, enabled=True, environment="test"),
    )
    assert result.complete and not result.utterances and not result.unlocated
