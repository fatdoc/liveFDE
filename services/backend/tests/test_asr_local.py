"""Local provider boundary tests; doubles are not accuracy measurements."""

import asyncio

import numpy as np
import pytest
import soundfile as sf

from live_review.integrations.asr_gateway.contracts import ASRError, ASRRequest, ASRSegment
from live_review.integrations.asr_gateway.local import (
    LocalASRProvider,
    LocalConfig,
    unload_local_models,
)
from live_review.integrations.asr_gateway.local import cache as cache_module
from live_review.integrations.asr_gateway.local import provider as provider_module
from live_review.integrations.asr_gateway.local.locking import inference_lock
from live_review.integrations.asr_gateway.local.models import model_path, resolve_device
from live_review.integrations.asr_gateway.local.observations import Observation, cluster_speakers


def test_missing_weights_never_invoke_hub(tmp_path, monkeypatch):
    monkeypatch.setattr(provider_module, "dependencies_available", lambda: True)
    provider = LocalASRProvider(LocalConfig(model_root=tmp_path))
    health = asyncio.run(provider.health())
    assert not health.ready and health.reason == "local_model_missing"
    with pytest.raises(ASRError, match="local_model_missing"):
        asyncio.run(
            provider.transcribe_file(tmp_path / "audio.wav", ASRRequest(request_id="missing"))
        )


def test_model_path_cannot_escape(tmp_path):
    with pytest.raises(ASRError, match="local_model_unsupported"):
        model_path(LocalConfig(model_root=tmp_path), "../other")


def test_device_explicit_and_auto(monkeypatch):
    import sys
    from types import SimpleNamespace

    torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    monkeypatch.setitem(sys.modules, "torch", torch)
    assert resolve_device("auto") == "cpu"
    with pytest.raises(ASRError, match="local_cuda_unavailable"):
        resolve_device("cuda")
    with pytest.raises(ASRError, match="local_mps_unsupported"):
        resolve_device("mps")
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    assert resolve_device("auto") == "cuda"
    assert resolve_device("cuda") == "cuda"


def test_file_wide_speaker_consistency(tmp_path):
    observations = [
        Observation(ASRSegment(id=str(i), text="test"), np.array(vector))
        for i, vector in enumerate(([1.0, 0.0], [0.0, 1.0], [1.0, 0.0]))
    ]
    result = cluster_speakers(observations, LocalConfig(model_root=tmp_path))
    assert [s.speaker_id for s in result] == ["speaker-01", "speaker-02", "speaker-01"]
    assert all(s.speaker_name is None and s.speaker_source == "clustering" for s in result)


def _stub(monkeypatch, tmp_path):
    monkeypatch.setattr(LocalASRProvider, "_preflight", lambda *args: None)
    state = {"clear": 0}

    class FakeModels:
        def __init__(self, config):
            self.config = config

        def clear(self):
            state["clear"] += 1

    monkeypatch.setattr(cache_module, "Models", FakeModels)

    def analyze(models, audio, request, *, offset_ms=0, first_index=0, windowed=False):
        return [
            Observation(
                ASRSegment(
                    id=str(first_index),
                    text="mock speech",
                    start_ms=offset_ms,
                    end_ms=offset_ms + len(audio) // 16,
                    timestamp_source="vad",
                )
            )
        ]

    monkeypatch.setattr(provider_module, "analyze_audio", analyze)
    return LocalASRProvider(LocalConfig(model_root=tmp_path, stream_window_ms=1000)), state


def test_stream_partial_precedes_eof_and_keeps_offsets(tmp_path, monkeypatch):
    provider, state = _stub(monkeypatch, tmp_path)

    async def scenario():
        saw_partial = False

        async def chunks():
            yield b"\0" * 32000
            assert saw_partial, "provider consumed next chunk before partial"
            yield b"\0" * 32000

        events = []
        async for event in provider.transcribe_stream(chunks(), ASRRequest(request_id="stream")):
            if event.type == "partial":
                saw_partial = True
                assert not event.segment.final
            events.append(event)
        result = events[-1].result
        assert result.duration_ms == 2000 and result.complete
        assert [(s.start_ms, s.end_ms) for s in result.segments] == [(0, 1000), (1000, 2000)]
        assert state["clear"] == 0
        await unload_local_models()
        assert state["clear"] == 1

    asyncio.run(scenario())


def test_stream_limits_and_odd_pcm(tmp_path, monkeypatch):
    provider, state = _stub(monkeypatch, tmp_path)

    async def run(data, limit=600):
        async def chunks():
            for part in data:
                yield part

        return [
            event
            async for event in provider.transcribe_stream(
                chunks(), ASRRequest(request_id="bad", max_duration_seconds=limit)
            )
        ]

    for parts, code, limit in [
        ([b"\0" * 32001], "chunk_invalid", 600),
        ([b"\0" * 801], "pcm_invalid", 600),
        ([b"\0" * 32000, b"\0" * 32000], "duration_exceeded", 1),
    ]:
        with pytest.raises(ASRError, match=code):
            asyncio.run(run(parts, limit))
    assert state["clear"] == 3


def test_reject_rate_and_duration_before_loading(tmp_path, monkeypatch):
    provider, state = _stub(monkeypatch, tmp_path)
    path = tmp_path / "wrong.wav"
    sf.write(path, np.zeros(8000), 8000)
    with pytest.raises(ASRError, match="requires_16k_mono"):
        asyncio.run(provider.transcribe_file(path, ASRRequest(request_id="rate")))
    sf.write(path, np.zeros(32000), 16000)
    with pytest.raises(ASRError, match="duration_exceeded"):
        asyncio.run(
            provider.transcribe_file(
                path, ASRRequest(request_id="duration", max_duration_seconds=1)
            )
        )
    assert state["clear"] == 0


def test_lock_releases_on_cancellation(tmp_path):
    async def scenario():
        async with inference_lock(tmp_path, 1):

            async def contender():
                async with inference_lock(tmp_path, 1):
                    pytest.fail("must remain locked")

            task = asyncio.create_task(contender())
            await asyncio.sleep(0.1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        async with inference_lock(tmp_path, 1):
            pass

    asyncio.run(scenario())


def test_cancel_waits_for_model_thread_before_unlock(tmp_path):
    import threading

    entered, release = threading.Event(), threading.Event()

    def blocking():
        entered.set()
        release.wait(5)

    async def scenario():
        async def worker():
            async with inference_lock(tmp_path, 1):
                await provider_module._run(blocking)

        task = asyncio.create_task(worker())
        await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        await asyncio.sleep(0.05)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        async with inference_lock(tmp_path, 1):
            pass

    asyncio.run(scenario())


def test_lock_blocks_another_process(tmp_path):
    import subprocess
    import sys

    script = (
        "import fcntl,sys; f=open(sys.argv[1],'a+'); fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)"
    )

    async def scenario():
        async with inference_lock(tmp_path, 1):
            result = subprocess.run(
                [sys.executable, "-c", script, str(tmp_path / ".inference.lock")],
                capture_output=True,
                check=False,
            )
            assert result.returncode != 0 and b"BlockingIOError" in result.stderr
        result = subprocess.run(
            [sys.executable, "-c", script, str(tmp_path / ".inference.lock")],
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0

    asyncio.run(scenario())


@pytest.fixture(autouse=True)
def clear_process_cache():
    asyncio.run(unload_local_models())
    yield
    asyncio.run(unload_local_models())


def test_models_reused_across_provider_instances(tmp_path, monkeypatch):
    provider, state = _stub(monkeypatch, tmp_path)

    async def scenario():
        async with cache_module.model_lease(provider.config) as first:
            pass
        async with cache_module.model_lease(provider.config) as second:
            assert first is second
        assert state["clear"] == 0
        await unload_local_models()
        assert state["clear"] == 1

    asyncio.run(scenario())


def test_cache_idle_evicts_residency_lock(tmp_path, monkeypatch):
    provider, state = _stub(monkeypatch, tmp_path)
    config = provider.config.model_copy(update={"cache_idle_seconds": 1})

    async def scenario():
        async with cache_module.model_lease(config):
            pass
        await asyncio.sleep(1.2)
        assert state["clear"] == 1
        async with inference_lock(tmp_path, 1):
            pass

    asyncio.run(scenario())


def test_short_speech_has_no_invented_speaker(tmp_path):
    from live_review.integrations.asr_gateway.local.observations import analyze_audio

    config = LocalConfig(model_root=tmp_path)

    class FakeModels:
        def __init__(self):
            self.config = config

        def generate(self, name, data, **kwargs):
            if name == config.vad_model:
                return [{"value": [[0, 600]]}]
            if name == config.asr_model:
                return [{"text": "short"}]
            pytest.fail("short speech must not reach speaker model")

    observed = analyze_audio(
        FakeModels(), np.zeros(9600), ASRRequest(request_id="short", speaker=True)
    )
    result = cluster_speakers(observed, config)
    assert result[0].speaker_id is None
    assert result[0].speaker_source == "unavailable"


def test_forced_segmentation_has_window_provenance(tmp_path):
    from live_review.integrations.asr_gateway.local.observations import analyze_audio

    config = LocalConfig(model_root=tmp_path, vad_max_segment_ms=1000)

    class FakeModels:
        def __init__(self):
            self.config = config

        def generate(self, name, data, **kwargs):
            return [{"value": [[0, 2100]]}] if name == config.vad_model else [{"text": "speech"}]

    result = analyze_audio(FakeModels(), np.zeros(33600), ASRRequest(request_id="window"))
    assert all(item.segment.timestamp_source == "vad_window" for item in result)


def test_punctuation_restoration_preserves_numeric_and_word_syntax():
    from live_review.integrations.asr_gateway.local.observations import punctuation_input

    assert punctuation_input("时间：9:00，金额3.5元。Don't stop!") == "时间9:00金额3.5元Don't stop"

    assert punctuation_input("Hello,world.") == "Hello world"


@pytest.mark.parametrize("outputs", [[[]], [[{"text": "   "}]], [[{"text": "speech"}], []]])
def test_vad_speech_without_asr_text_fails_file_and_stream(tmp_path, monkeypatch, outputs):
    from live_review.integrations.asr_gateway.local import observations as observation_module

    provider, _ = _stub(monkeypatch, tmp_path)
    # Exercise the real observation path through both provider entry points.
    monkeypatch.setattr(provider_module, "analyze_audio", observation_module.analyze_audio)

    class EmptyASRModels:
        def __init__(self, config):
            self.config = config
            self.index = 0

        def generate(self, name, data, **kwargs):
            if name == self.config.vad_model:
                return [{"value": [[i * 500, (i + 1) * 500] for i in range(len(outputs))]}]
            value = outputs[self.index]
            self.index += 1
            return value

        def clear(self):
            pass

    monkeypatch.setattr(cache_module, "Models", EmptyASRModels)
    path = tmp_path / "speech.wav"
    sf.write(path, np.zeros(16000), 16000)
    with pytest.raises(ASRError, match="local_asr_empty_for_speech"):
        asyncio.run(provider.transcribe_file(path, ASRRequest(request_id="empty-file")))

    async def stream():
        async def chunks():
            yield b"\0" * 32000

        events = []
        try:
            async for event in provider.transcribe_stream(
                chunks(), ASRRequest(request_id="empty-stream")
            ):
                events.append(event)
        finally:
            assert not any(event.type == "completed" for event in events)

    with pytest.raises(ASRError, match="local_asr_empty_for_speech"):
        asyncio.run(stream())


def test_explicit_no_vad_speech_is_valid_empty_result(tmp_path, monkeypatch):
    from live_review.integrations.asr_gateway.local import observations as observation_module

    provider, _ = _stub(monkeypatch, tmp_path)
    monkeypatch.setattr(provider_module, "analyze_audio", observation_module.analyze_audio)

    class SilentModels:
        def __init__(self, config):
            self.config = config

        def generate(self, name, data, **kwargs):
            assert name == self.config.vad_model
            return [{"value": []}]

        def clear(self):
            pass

    monkeypatch.setattr(cache_module, "Models", SilentModels)
    path = tmp_path / "silence.wav"
    sf.write(path, np.zeros(16000), 16000)
    result = asyncio.run(provider.transcribe_file(path, ASRRequest(request_id="silence")))
    assert result.complete and not result.segments


@pytest.mark.parametrize(
    "vad,code",
    [([], "local_vad_result_invalid"), ([{"value": [[0, 10]]}], "local_speech_segment_too_short")],
)
def test_missing_vad_or_unprocessable_speech_does_not_become_silence(tmp_path, vad, code):
    from live_review.integrations.asr_gateway.local.observations import analyze_audio

    class BoundaryModels:
        config = LocalConfig(model_root=tmp_path)

        def generate(self, name, data, **kwargs):
            assert name == self.config.vad_model
            return vad

    with pytest.raises(ASRError, match=code):
        analyze_audio(BoundaryModels(), np.zeros(16000), ASRRequest(request_id="boundary"))
