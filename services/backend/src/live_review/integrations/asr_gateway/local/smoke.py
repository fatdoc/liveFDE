"""Explicit offline smoke against the provisioned public Nano Chinese sample."""

import argparse
import asyncio
import json
import math
import sys
import time
from pathlib import Path

from ..contracts import ASRRequest
from .cache import unload_local_models
from .config import LocalConfig
from .provider import LocalASRProvider


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("model_root", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--observations", action="store_true")
    parser.add_argument("--punctuation", action="store_true")
    args = parser.parse_args()
    outbound_attempts = []

    def deny_network(event, values):
        if event == "socket.connect":
            outbound_attempts.append(event)
            raise RuntimeError("smoke_network_forbidden")

    sys.addaudithook(deny_network)
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly

    root = args.model_root.resolve()
    audio, rate = sf.read(root / "Fun-ASR-Nano-2512/example/zh.mp3", dtype="float32")
    if audio.ndim != 1:
        audio = audio.mean(axis=1)
    divisor = math.gcd(rate, 16000)
    audio = resample_poly(audio, 16000 // divisor, rate // divisor).astype(np.float32)
    wav = args.output_json.parent / "public-zh-16k.wav"
    sf.write(wav, audio, 16000, subtype="PCM_16")
    config = LocalConfig(
        model_root=root,
        stream_window_ms=5000,
        punctuation_model="ct-punc" if args.punctuation else None,
    )
    request = ASRRequest(
        request_id="local-public-smoke",
        speaker=args.observations,
        emotion=args.observations,
        language="zh",
        max_duration_seconds=30,
    )

    async def scenario():
        provider = LocalASRProvider(config)
        health = await provider.health()
        file_result = await provider.transcribe_file(wav, request)
        warm_file_result = await provider.transcribe_file(wav, request)
        pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
        consumed = 0
        eof = False
        first_partial = None
        began = time.monotonic()

        async def chunks():
            nonlocal consumed, eof
            for offset in range(0, len(pcm), 3200):
                consumed += min(3200, len(pcm) - offset)
                yield pcm[offset : offset + 3200]
            eof = True

        events = []
        async for event in provider.transcribe_stream(chunks(), request):
            if event.type == "partial" and first_partial is None:
                first_partial = {
                    "before_eof": not eof,
                    "consumed_audio_ms": consumed // 32,
                    "elapsed_seconds": time.monotonic() - began,
                }
            events.append(event)
        await unload_local_models()
        return {
            "health": health.model_dump(mode="json"),
            "file": file_result.model_dump(mode="json"),
            "warm_file": warm_file_result.model_dump(mode="json"),
            "first_partial": first_partial,
            "stream": events[-1].result.model_dump(mode="json"),
            "outbound_attempts": len(outbound_attempts),
            "accuracy_metrics": "not_computed_by_smoke;see_separate_reference_evaluation",
        }

    result = asyncio.run(scenario())
    args.output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"smoke_result={args.output_json}", flush=True)


if __name__ == "__main__":
    main()
