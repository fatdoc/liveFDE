"""One durable intent per immutable audio chunk; never replay unknown provider outcomes."""

from live_review.integrations.asr import ASRUnknownCall, SegmentTranscript
from live_review.integrations.media.process import MediaError, check_cancel
from live_review.modules.jobs.execution import UnknownCall
from live_review.workers.media_artifacts import read_json, write_json


class RecordedASR:
    def __init__(self, context, provider, root, directory, max_requests, max_duration_seconds):
        self.context, self.inner = context, provider
        self.root, self.directory = root, directory
        self.provider, self.model, self.synthetic = (
            provider.provider,
            provider.model,
            provider.synthetic,
        )
        self.max_requests, self.max_samples = max_requests, max_duration_seconds * 16000

    def preflight(self, segments):
        if len(segments) > self.max_requests:
            raise MediaError("asr_request_budget_exceeded")
        if sum(s.end_sample - s.start_sample for s in segments) > self.max_samples:
            raise MediaError("asr_duration_budget_exceeded")
        inner_preflight = getattr(self.inner, "preflight", None)
        if inner_preflight:
            inner_preflight(segments)

    def transcribe_segment(self, segment, audio_path, *, cancel=None):
        check_cancel(cancel)
        key = f"audio-{segment.index}-{segment.artifact.sha256}"
        try:
            call = self.context.begin_paid_call(key)
        except UnknownCall:
            raise ASRUnknownCall from None
        if not call["execute"]:
            cached = call["result"]
            if cached["kind"] == "error":
                raise MediaError(cached["code"])
            return SegmentTranscript.model_validate(read_json(self.root, cached["reference"]))
        try:
            result = self.inner.transcribe_segment(segment, audio_path, cancel=cancel)
        except ASRUnknownCall:
            raise
        except MediaError as error:
            self.context.finish_paid_call(call["intent_id"], {"kind": "error", "code": error.code})
            raise
        except Exception:
            # Unknown provider exceptions may occur after sending. Do not guess success/failure.
            raise ASRUnknownCall from None
        reference = write_json(self.root, self.directory, result.model_dump(mode="json"))
        self.context.finish_paid_call(
            call["intent_id"], {"kind": "response", "reference": reference}
        )
        return result
