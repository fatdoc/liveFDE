"""Local file and bounded-window streaming ASR provider."""

import asyncio
import time
from collections.abc import AsyncIterator
from pathlib import Path

from ..contracts import ASRError, ASREvent, ASRHealth, ASRRequest, ASRResult
from .cache import model_lease
from .config import LocalConfig
from .models import dependencies_available, model_path, resolve_device
from .observations import analyze_audio, cluster_speakers


async def _run(function, *args, **kwargs):
    # Cancellation cannot release the residency lock while a model thread still runs.
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()
        raise


class LocalASRProvider:
    def __init__(self, config: LocalConfig):
        self.config = config

    def _preflight(self, request):
        if request.language not in {"auto", "zh", "zh-CN", "en", "ja"}:
            raise ASRError("local_language_unsupported")
        if not dependencies_available():
            raise ASRError("local_dependencies_missing")
        resolve_device(self.config.device)
        names = [self.config.vad_model, self.config.asr_model]
        if request.speaker:
            names.append(self.config.speaker_model)
        if request.emotion:
            names.append(self.config.emotion_model)
        if request.punctuation and self.config.punctuation_model:
            names.append(self.config.punctuation_model)
        for name in names:
            model_path(self.config, name)

    async def health(self):
        try:
            self._preflight(ASRRequest(request_id="health"))
        except ASRError as error:
            return ASRHealth(
                provider="local", ready=False, reason=error.code, device=self.config.device
            )
        capabilities = ["file", "stream_windowed", "vad_timestamps", "native_punctuation"]
        for name, capability in (
            (self.config.speaker_model, "speaker_clustering"),
            (self.config.emotion_model, "emotion"),
            (self.config.punctuation_model, "punctuation"),
        ):
            if name:
                try:
                    model_path(self.config, name)
                    capabilities.append(capability)
                except ASRError:
                    pass
        return ASRHealth(
            provider="local",
            ready=True,
            reason="provisioned_lazy_not_loaded",
            device=resolve_device(self.config.device),
            capabilities=tuple(capabilities),
        )

    def _result(self, observations, duration_ms, started, streaming=False):
        warnings = [
            "timestamps_are_vad_or_vad_window_boundaries_not_word_alignment",
            "model_confidence_unavailable",
            "nano_native_punctuation",
        ]
        if streaming:
            warnings.append("bounded_window_asr_not_token_realtime;window_edges_may_split_words")
        return ASRResult(
            provider="local",
            model=self.config.asr_model,
            segments=cluster_speakers(observations, self.config),
            complete=True,
            duration_ms=duration_ms,
            elapsed_ms=int((time.monotonic() - started) * 1000),
            warnings=tuple(warnings),
            source="local",
        )

    async def transcribe_file(self, path: Path, request: ASRRequest) -> ASRResult:
        self._preflight(request)
        started = time.monotonic()
        import soundfile as sf

        try:
            info = sf.info(path)
            if info.samplerate != 16000 or info.channels != 1:
                raise ASRError("local_audio_requires_16k_mono")
            if info.frames > request.max_duration_seconds * 16000:
                raise ASRError("audio_duration_exceeded")
            if info.frames < 400:
                raise ASRError("audio_empty_or_too_short")
            async with model_lease(self.config) as models:
                audio, _ = await _run(sf.read, path, dtype="float32")
                observations = await _run(analyze_audio, models, audio, request)
                return await _run(self._result, observations, info.frames // 16, started)
        except ASRError:
            raise
        except Exception as error:
            raise ASRError("local_inference_failed") from error

    async def transcribe_stream(self, chunks: AsyncIterator[bytes], request: ASRRequest):
        self._preflight(request)
        import numpy as np

        started = time.monotonic()
        window_bytes = self.config.stream_window_ms * 32
        max_bytes = request.max_duration_seconds * 32000
        buffer = bytearray()
        received, processed = 0, 0
        observations = []
        try:
            async with model_lease(self.config) as models:
                async for chunk in chunks:
                    if not isinstance(chunk, bytes) or len(chunk) > window_bytes:
                        raise ASRError("local_stream_chunk_invalid")
                    received += len(chunk)
                    if received > max_bytes:
                        raise ASRError("audio_duration_exceeded")
                    buffer.extend(chunk)
                    while len(buffer) >= window_bytes:
                        data = bytes(buffer[:window_bytes])
                        del buffer[:window_bytes]
                        audio = np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768
                        found = await _run(
                            analyze_audio,
                            models,
                            audio,
                            request,
                            offset_ms=processed // 32,
                            first_index=len(observations),
                            windowed=True,
                        )
                        observations.extend(found)
                        processed += window_bytes
                        for item in found:
                            yield ASREvent(
                                type="partial",
                                segment=item.segment.model_copy(update={"final": False}),
                            )
                if received % 2 or received < 800:
                    raise ASRError("local_stream_pcm_invalid")
                if buffer:
                    audio = np.frombuffer(buffer, dtype="<i2").astype(np.float32) / 32768
                    found = await _run(
                        analyze_audio,
                        models,
                        audio,
                        request,
                        offset_ms=processed // 32,
                        first_index=len(observations),
                        windowed=True,
                    )
                    observations.extend(found)
                result = await _run(self._result, observations, received // 32, started, True)
            for segment in result.segments:
                yield ASREvent(type="final", segment=segment)
            yield ASREvent(type="completed", result=result)
        except ASRError:
            raise
        except Exception as error:
            raise ASRError("local_inference_failed") from error
