"""Gateway-specific routes. No defaults are added to existing v1/v2 route variants."""

from pathlib import PurePosixPath
from typing import Literal

from pydantic import Field, field_validator

from live_review.core.provider_config import FrozenModel


class LocalASRRoute(FrozenModel):
    protocol: Literal["local_funasr"]
    enabled: bool = False
    provider: Literal["local"] = "local"
    model: str = "Fun-ASR-Nano-2512"
    key_env: None = None
    model_root: str
    worker_socket: str | None = None
    cache_idle_seconds: int = Field(default=60, ge=1, le=3600)
    device: Literal["cpu", "cuda", "mps", "auto"] = "cpu"
    vad_model: str = "fsmn-vad"
    speaker_model: str = "campplus"
    emotion_model: str = "emotion2vec_plus_base"
    punctuation_model: str | None = None
    vad_max_segment_ms: int = Field(default=15000, ge=1000, le=30000)
    stream_window_ms: int = Field(default=5000, ge=1000, le=15000)
    speaker_similarity_threshold: float = Field(default=0.65, gt=0, le=1)
    min_speaker_duration_ms: int = Field(default=2000, ge=400, le=30000)
    max_speakers: int = Field(default=16, ge=1, le=32)
    lock_timeout_seconds: int = Field(default=300, ge=1, le=1800)
    cpu_threads: int = Field(default=4, ge=1, le=32)

    @field_validator("model_root")
    @classmethod
    def absolute_root(cls, value):
        if not value.startswith("/") or any(x in value for x in ("$", "~", "\\")):
            raise ValueError("local_model_root_required")
        if ".." in PurePosixPath(value).parts:
            raise ValueError("invalid_model_root")
        return value


class TencentASRRoute(FrozenModel):
    protocol: Literal["tencent_asr"]
    enabled: bool = False
    provider: Literal["tencent"] = "tencent"
    model: str = "16k_zh"
    stream_model: Literal["16k_zh_en_2.0", "16k_zh_en_speaker_2.0"] = "16k_zh_en_speaker_2.0"
    key_env: str = Field(default="TENCENT_SECRET_KEY", pattern=r"^[A-Z][A-Z0-9_]{0,127}$")
    secret_id_env: str = Field(default="TENCENT_SECRET_ID", pattern=r"^[A-Z][A-Z0-9_]{0,127}$")
    app_id_env: str = Field(default="TENCENT_APP_ID", pattern=r"^[A-Z][A-Z0-9_]{0,127}$")
    timeout_seconds: int = Field(default=120, ge=1, le=600)
    poll_interval_seconds: int = Field(default=1, ge=1, le=30)
    max_poll_requests: int = Field(default=120, ge=1, le=600)
    io_timeout_seconds: int = Field(default=10, ge=1, le=60)
