"""Reuse LIVE-005 intents and artifact references for file/stream cloud outcomes."""

from live_review.integrations.asr_gateway.contracts import ASRError, ASRResult
from live_review.modules.jobs.execution import UnknownCall
from live_review.workers.media_artifacts import read_json, write_json


class CloudRecorder:
    def __init__(self, context, root, directory):
        self.context, self.root, self.directory = context, root, directory

    async def file(self, provider, path, request):
        try:
            call = self.context.begin_paid_call("gateway-cloud-file")
        except UnknownCall:
            raise ASRError("call_result_unknown", unknown=True) from None
        if not call["execute"]:
            known = call["result"]
            if known["kind"] == "error":
                raise ASRError(known["code"])
            return ASRResult.model_validate(read_json(self.root, known["reference"]))
        try:
            result = await provider.transcribe_file(path, request)
        except ASRError as error:
            if not error.unknown:
                self.context.finish_paid_call(
                    call["intent_id"], {"kind": "error", "code": error.code}
                )
            raise
        except BaseException:
            # Cancellation/disconnect is also unknown once a request may have been sent.
            raise ASRError("call_result_unknown", unknown=True) from None
        ref = write_json(self.root, self.directory, result.model_dump(mode="json"))
        self.context.finish_paid_call(call["intent_id"], {"kind": "response", "reference": ref})
        return result

    async def stream(self, provider, chunks, request):
        call = self.context.begin_paid_call("gateway-cloud-stream")
        if not call["execute"]:
            raise ASRError("stream_not_replayable", unknown=True)
        finished = False
        try:
            async for event in provider.transcribe_stream(chunks, request):
                if event.type == "completed" and event.result is not None:
                    ref = write_json(
                        self.root, self.directory, event.result.model_dump(mode="json")
                    )
                    self.context.finish_paid_call(
                        call["intent_id"], {"kind": "response", "reference": ref}
                    )
                    finished = True
                yield event
        except ASRError as error:
            if not error.unknown:
                self.context.finish_paid_call(
                    call["intent_id"], {"kind": "error", "code": error.code}
                )
            raise
        if not finished:
            raise ASRError("stream_result_unknown", unknown=True)
