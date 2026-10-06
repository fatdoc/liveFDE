"""Provider-independent ASR boundaries; unknown observations remain null."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ASRSegment(Contract):
    id: str
    text: str
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    speaker_id: str | None = None
    speaker_name: str | None = None
    emotion: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    emotion_confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    timestamp_source: Literal["vad", "vad_window", "provider", "unavailable"] = "unavailable"
    speaker_source: Literal["clustering", "provider", "unavailable"] = "unavailable"
    emotion_source: Literal["model", "provider", "unavailable"] = "unavailable"
    final: bool = True

    @model_validator(mode="after")
    def interval(self):
        if (self.start_ms is None) != (self.end_ms is None):
            raise ValueError("incomplete_interval")
        if self.start_ms is not None and self.end_ms < self.start_ms:
            raise ValueError("invalid_interval")
        if self.speaker_name is not None:
            raise ValueError("speaker_identity_not_enrolled")
        return self


class ASRRequest(Contract):
    speaker: bool = False
    emotion: bool = False
    punctuation: bool = True
    language: str = "auto"
    max_duration_seconds: int = Field(default=600, ge=1, le=14400)
    # Trusted gateway builds this from persisted task authorization, never model YAML.
    allow_network: bool = False
    privacy: Literal["local_only", "cloud_allowed"] = "local_only"
    request_id: str


class ASRMetadata(Contract):
    complete: bool
    source: Literal["local", "cloud"]
    timestamp_sources: tuple[str, ...]
    speaker_sources: tuple[str, ...]
    emotion_sources: tuple[str, ...]


class ASRResult(Contract):
    provider: str
    model: str
    text: str = ""
    language: str | None = None
    metadata: ASRMetadata | None = None
    segments: tuple[ASRSegment, ...]
    complete: bool
    duration_ms: int = Field(ge=0)
    elapsed_ms: int = Field(ge=0)
    warnings: tuple[str, ...] = ()
    synthetic: bool = False
    source: Literal["local", "cloud"]

    @model_validator(mode="after")
    def public_summary(self):
        object.__setattr__(self, "text", "".join(segment.text for segment in self.segments))
        object.__setattr__(
            self,
            "metadata",
            ASRMetadata(
                complete=self.complete,
                source=self.source,
                timestamp_sources=tuple(sorted({s.timestamp_source for s in self.segments})),
                speaker_sources=tuple(sorted({s.speaker_source for s in self.segments})),
                emotion_sources=tuple(sorted({s.emotion_source for s in self.segments})),
            ),
        )
        return self


class ASREvent(Contract):
    type: Literal["partial", "final", "error", "completed"]
    segment: ASRSegment | None = None
    result: ASRResult | None = None
    code: str | None = None


class ASRHealth(Contract):
    provider: str
    ready: bool
    reason: str | None = None
    device: str | None = None
    capabilities: tuple[str, ...] = ()
    network_checked: bool = False


class ASRError(Exception):
    def __init__(self, code: str, *, unknown: bool = False):
        self.code, self.unknown = code, unknown
        super().__init__(code)


class ASRProvider(Protocol):
    async def transcribe_file(self, path: Path, request: ASRRequest) -> ASRResult: ...
    def transcribe_stream(
        self, chunks: AsyncIterator[bytes], request: ASRRequest
    ) -> AsyncIterator[ASREvent]: ...
    async def health(self) -> ASRHealth: ...
