"""Explicit synthetic responses. Never listens to audio or calls a network service."""

import json
from pathlib import Path

from live_review.integrations.asr.models import SegmentTranscript
from live_review.integrations.media.process import MediaError, check_cancel


class OfflineFixtureProvider:
    provider = "synthetic"
    model = "fixture-v1"
    synthetic = True

    def __init__(self, payload: dict, *, enabled: bool = False, environment: str):
        if not enabled or environment not in {"development", "test"}:
            raise MediaError("offline_fixture_not_allowed")
        if not isinstance(payload, dict) or set(payload) != {"segments"}:
            raise MediaError("invalid_fixture")
        if not isinstance(payload["segments"], dict) or len(json.dumps(payload)) > 1024 * 1024:
            raise MediaError("invalid_fixture")
        # Copy caller data so later mutation cannot alter an in-flight fixture.
        self._segments = json.loads(json.dumps(payload["segments"]))

    @classmethod
    def from_file(cls, path: Path, *, enabled: bool = False, environment: str):
        if path.stat().st_size > 1024 * 1024:
            raise MediaError("fixture_size_limit")
        return cls(
            json.loads(path.read_text(encoding="utf-8")), enabled=enabled, environment=environment
        )

    def transcribe_segment(self, segment, audio_path, *, cancel=None):
        check_cancel(cancel)
        response = self._segments.get(str(segment.index))
        if response is None:
            raise MediaError("segment_missing")
        if response == {"fail": True}:
            raise MediaError("provider_segment_failed")
        return SegmentTranscript.model_validate(response)
