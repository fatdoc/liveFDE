import wave
from pathlib import Path

from live_review.integrations.asr.models import ASRProvider, SegmentOutcome, Transcript, Utterance
from live_review.integrations.media.files import verify_artifact
from live_review.integrations.media.models import Extraction
from live_review.integrations.media.pipeline import milliseconds
from live_review.integrations.media.process import Cancel, MediaError, check_cancel


def _validate_audio(extraction: Extraction, root: Path):
    path = verify_artifact(root, extraction.audio)
    with wave.open(str(path), "rb") as audio:
        if (
            audio.getnframes(),
            audio.getframerate(),
            audio.getnchannels(),
            audio.getsampwidth(),
        ) != (extraction.audio_samples, 16000, 1, 2):
            raise MediaError("audio_manifest_mismatch")
    cursor = 0
    if not extraction.segments:
        raise MediaError("segments_missing")
    for index, segment in enumerate(extraction.segments):
        if (
            segment.index != index
            or segment.start_sample != cursor
            or segment.end_sample <= cursor
            or segment.start_ms != extraction.audio_offset_ms + milliseconds(cursor)
            or segment.end_ms != extraction.audio_offset_ms + milliseconds(segment.end_sample)
        ):
            raise MediaError("segment_timeline_invalid")
        cursor = segment.end_sample
    if cursor != extraction.audio_samples:
        raise MediaError("segment_coverage_incomplete")


def _merge(segment, response):
    results, issue, previous_end = [], None, 0
    duration = segment.end_ms - segment.start_ms
    for item in response.utterances:
        if item.start_ms is None or item.end_ms is None:
            issue = "timestamp_missing"
            continue
        if not 0 <= item.start_ms < item.end_ms <= duration:
            issue = "timestamp_out_of_range"
            continue
        if item.start_ms < previous_end:
            issue = "timestamp_overlap_or_order"
            continue
        previous_end = item.end_ms
        results.append(
            Utterance(
                segment_index=segment.index,
                text=item.text,
                start_ms=segment.start_ms + item.start_ms,
                end_ms=segment.start_ms + item.end_ms,
            )
        )
    if response.missing_words:
        issue = issue or "words_missing"
    if response.coverage != "full":
        issue = issue or "coverage_incomplete"
    if not results and not response.no_speech:
        issue = issue or "empty_transcript"
    if results and response.no_speech:
        issue = issue or "conflicting_speech_state"
    return SegmentOutcome(
        segment_index=segment.index,
        status="partial" if issue else "complete",
        error_code=issue,
        utterances=tuple(results),
    )


def transcribe(
    extraction: Extraction, *, artifact_root: Path, provider: ASRProvider, cancel: Cancel = None
) -> Transcript:
    """Provider is explicit. This orchestration never chooses or retries a vendor."""
    check_cancel(cancel)
    _validate_audio(extraction, artifact_root)
    preflight = getattr(provider, "preflight", None)
    if preflight:
        preflight(extraction.segments)
    outcomes = []
    text_size, utterance_count = 0, 0
    for segment in extraction.segments:
        check_cancel(cancel)
        try:
            path = verify_artifact(artifact_root, segment.artifact)
            with wave.open(str(path), "rb") as audio:
                if (
                    audio.getframerate(),
                    audio.getnchannels(),
                    audio.getsampwidth(),
                    audio.getnframes(),
                ) != (16000, 1, 2, segment.end_sample - segment.start_sample):
                    raise MediaError("segment_audio_mismatch")
            response = provider.transcribe_segment(segment, path, cancel=cancel)
            outcome = _merge(segment, response)
            text_size += sum(len(item.text) for item in outcome.utterances)
            utterance_count += len(outcome.utterances)
            if text_size > 1024 * 1024 or utterance_count > 10000:
                raise MediaError("transcript_size_limit")
            outcomes.append(outcome)
        except MediaError as error:
            if error.code in {"canceled", "call_result_unknown", "transcript_size_limit"}:
                raise
            outcomes.append(
                SegmentOutcome(segment_index=segment.index, status="failed", error_code=error.code)
            )
        except Exception:
            # Provider exceptions may contain tokens/transcripts; expose no raw text.
            outcomes.append(
                SegmentOutcome(
                    segment_index=segment.index,
                    status="failed",
                    error_code="provider_invalid_or_failed",
                )
            )
    complete = all(result.status == "complete" for result in outcomes)
    status = (
        "complete"
        if complete
        else ("failed" if all(result.status == "failed" for result in outcomes) else "partial")
    )
    utterances = tuple(item for result in outcomes for item in result.utterances)
    if sum(len(item.text) for item in utterances) > 1024 * 1024:
        raise MediaError("transcript_size_limit")
    return Transcript(
        source_sha256=extraction.source_sha256,
        audio_sha256=extraction.audio.sha256,
        provider=provider.provider,
        model=provider.model,
        synthetic=provider.synthetic,
        status=status,
        complete=complete,
        segments=tuple(outcomes),
        utterances=utterances,
    )
