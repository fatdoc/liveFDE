from pathlib import Path
from typing import Literal, Protocol

from pydantic import Field

from live_review.integrations.media.models import AudioSegment, FrozenModel
from live_review.integrations.media.process import Cancel


class LocalUtterance(FrozenModel):
    text: str = Field(min_length=1, max_length=10000)
    start_ms: int | None = None
    end_ms: int | None = None


class SegmentTranscript(FrozenModel):
    utterances: tuple[LocalUtterance, ...] = Field(default=(), max_length=2000)
    coverage: Literal["full", "partial", "unknown"] = "unknown"
    missing_words: bool = True
    no_speech: bool = False
    raw_text: str | None = Field(default=None, max_length=1024 * 1024)


class ASRProvider(Protocol):
    provider: str
    model: str
    synthetic: bool

    def transcribe_segment(
        self, segment: AudioSegment, audio_path: Path, *, cancel: Cancel = None
    ) -> SegmentTranscript: ...


class Utterance(FrozenModel):
    segment_index: int
    text: str
    start_ms: int
    end_ms: int


class UnlocatedUtterance(FrozenModel):
    segment_index: int
    text: str
    start_ms: None = None
    end_ms: None = None
    reason: str


class SegmentOutcome(FrozenModel):
    segment_index: int
    status: Literal["complete", "partial", "failed"]
    error_code: str | None = None
    utterances: tuple[Utterance, ...] = ()
    unlocated: tuple[UnlocatedUtterance, ...] = ()
    raw_text: str | None = None


class Transcript(FrozenModel):
    schema_version: Literal[1] = 1
    source_sha256: str
    audio_sha256: str
    provider: str
    model: str
    synthetic: bool
    status: Literal["complete", "partial", "failed"]
    complete: bool
    segments: tuple[SegmentOutcome, ...]
    utterances: tuple[Utterance, ...]
    unlocated: tuple[UnlocatedUtterance, ...] = ()
    timestamp_unit: Literal["milliseconds"] = "milliseconds"
    timeline: Literal["source_relative"] = "source_relative"
