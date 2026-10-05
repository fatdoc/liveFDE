"""Serializable immutable media contracts; paths are relative to an artifact root."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    def to_dict(self):
        return self.model_dump(mode="json")


class Artifact(FrozenModel):
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(gt=0)


class AudioSegment(FrozenModel):
    index: int = Field(ge=0)
    start_sample: int = Field(ge=0)
    end_sample: int = Field(gt=0)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    artifact: Artifact


class Extraction(FrozenModel):
    schema_version: Literal[1] = 1
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_size_bytes: int = Field(gt=0)
    source_duration_ms: int | None = Field(default=None, ge=0)
    source_integrity: Literal["verified_snapshot"] = "verified_snapshot"
    source_audio_stream_index: int = Field(ge=0)
    audio_offset_ms: int = Field(ge=0)
    audio_samples: int = Field(gt=0)
    sample_rate: Literal[16000] = 16000
    channels: Literal[1] = 1
    sample_width_bytes: Literal[2] = 2
    audio_duration_ms: int = Field(gt=0)
    audio: Artifact
    segments: tuple[AudioSegment, ...]
    ffmpeg_version: str
    ffprobe_version: str
    coverage: Literal["decoded_audio_track"] = "decoded_audio_track"
