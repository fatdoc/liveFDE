"""Provider observations only; no identity inference or invented confidence."""

from live_review.integrations.asr_gateway.contracts import ASRResult, ASRSegment


def segment(identifier, text, start, end, speaker, emotion=None, *, final=True, duration_ms):
    times = type(start) is int and type(end) is int and 0 <= start < end <= duration_ms
    speaker_id = str(speaker) if type(speaker) is int and speaker >= 0 else None
    return ASRSegment(
        id=str(identifier),
        text=text,
        start_ms=start if times else None,
        end_ms=end if times else None,
        speaker_id=speaker_id,
        emotion=emotion,
        timestamp_source="provider" if times else "unavailable",
        speaker_source="provider" if speaker_id is not None else "unavailable",
        emotion_source="provider" if emotion else "unavailable",
        final=final,
    )


def result(model, segments, request, duration_ms, elapsed_ms, *, ended=True, warnings=()):
    notes = set(warnings)
    complete = ended and bool(segments)
    for item in segments:
        if not item.text.strip() or item.start_ms is None or not item.final:
            complete = False
            notes.add("transcript_incomplete")
        if request.speaker and item.speaker_id is None:
            notes.add("speaker_unavailable")
        if request.emotion and item.emotion is None:
            notes.add("emotion_unavailable")
    if not segments:
        notes.add("no_explicit_speech_result")
    return ASRResult(
        provider="tencent",
        model=model,
        segments=tuple(segments),
        complete=complete,
        duration_ms=duration_ms,
        elapsed_ms=elapsed_ms,
        warnings=tuple(sorted(notes)),
        source="cloud",
    )


def file_segments(data, request, duration_ms):
    rows = data.get("ResultDetail")
    if not isinstance(rows, list):
        rows = []
    parsed = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError("invalid_result_row")
        text = row.get("FinalSentence")
        if not isinstance(text, str):
            raise ValueError("invalid_result_text")
        emotions = row.get("EmotionType", [])
        emotion = (
            emotions[0]
            if request.emotion
            and isinstance(emotions, list)
            and len(emotions) == 1
            and isinstance(emotions[0], str)
            else None
        )
        parsed.append(
            segment(
                index,
                text,
                row.get("StartMs"),
                row.get("EndMs"),
                row.get("SpeakerId") if request.speaker else None,
                emotion,
                duration_ms=duration_ms,
            )
        )
    if not parsed and isinstance(data.get("Result"), str) and data["Result"]:
        parsed.append(
            segment("unlocated", data["Result"], None, None, None, duration_ms=duration_ms)
        )
    return parsed
