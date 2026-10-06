"""Explicit provisioned paths: inference never acquires model weights."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LocalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    model_root: Path
    device: Literal["cpu", "cuda", "auto", "mps"] = "cpu"
    vad_model: Literal["fsmn-vad"] = "fsmn-vad"
    asr_model: Literal["Fun-ASR-Nano-2512"] = "Fun-ASR-Nano-2512"
    speaker_model: Literal["campplus"] = "campplus"
    emotion_model: Literal["emotion2vec_plus_base"] = "emotion2vec_plus_base"
    punctuation_model: Literal["ct-punc"] | None = None
    sample_rate: Literal[16000] = 16000
    vad_max_segment_ms: int = Field(default=15000, ge=1000, le=30000)
    stream_window_ms: int = Field(default=5000, ge=1000, le=15000)
    speaker_similarity_threshold: float = Field(default=0.65, ge=0, le=1)
    max_speakers: int = Field(default=16, ge=1, le=64)
    lock_timeout_seconds: float = Field(default=300, ge=1, le=3600)
    cpu_threads: int = Field(default=4, ge=1, le=32)

    cache_idle_seconds: float = Field(default=60, ge=1, le=3600)

    min_speaker_duration_ms: int = Field(default=2000, ge=400, le=30000)
