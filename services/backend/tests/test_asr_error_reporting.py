"""Synthetic cross-process diagnostics; no database, model, or provider calls."""

import multiprocessing
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest

from live_review.integrations.asr_gateway.contracts import ASRError
from live_review.integrations.asr_gateway.local_worker.protocol import SAFE_CODES, safe_code
from live_review.modules.jobs.execution import Canceled, LostLease, UnknownCall
from live_review.workers import handler_process, job_runner
from live_review.workers.handler_process import ASRHandlerFailed, StopUnconfirmed, error_payload
from live_review.workers.handlers import HandlerUnavailable


class MaliciousError(Exception):
    code = "local_vad_result_invalid"


def synthetic_child(connection, parent_pid, code):
    # Only dependency boundaries are replaced; exercise the actual child exception/pipe path.
    handler_process.build_engine = lambda _: SimpleNamespace(dispose=lambda: None)
    handler_process.Context = lambda *args: None

    def fail(context):
        raise ASRError(code)

    handler_process.resolve = lambda *args: fail
    handler_process._child(
        connection, parent_pid, SimpleNamespace(job_lease_seconds=10), None, None, None, "fixture"
    )


@pytest.mark.parametrize(
    "code",
    [
        "local_vad_result_invalid",
        "local_asr_empty_for_speech",
        "secret=/audio/raw.wav\nCookie=private",
    ],
)
def test_actual_child_pipe_retains_only_safe_asr_code(code):
    factory = multiprocessing.get_context("spawn")
    parent, child = factory.Pipe()
    process = factory.Process(target=synthetic_child, args=(child, os.getpid(), code))
    process.start()
    child.close()
    try:
        parent.send("alive")
        assert parent.poll(10)
        payload = parent.recv()
        assert payload == ("asr_failed", code if code in SAFE_CODES else "worker_failed")
        process.join(5)
        assert process.exitcode == 0
    finally:
        if process.is_alive():
            process.kill()
            process.join(5)
        parent.close()


@pytest.mark.parametrize(
    "code",
    [
        None,
        [],
        {"secret": "private"},
        "path=/private.wav",
        "local_vad_result_invalid\nsecret",
        "unregistered_code",
    ],
)
def test_parent_revalidates_untrusted_diagnostic(code):
    assert ASRHandlerFailed(code).code == "worker_failed"
    assert str(ASRHandlerFailed(code)) == "worker_failed"


def test_error_categories_take_precedence_and_never_accept_arbitrary_exception_code():
    for error, category in [
        (LostLease(), "lost"),
        (Canceled(), "canceled"),
        (UnknownCall(), "unknown"),
        (HandlerUnavailable(), "unavailable"),
    ]:
        error.code = "local_vad_result_invalid"
        assert error_payload(error) == (category, None)
    assert error_payload(MaliciousError("private exception text")) == ("failed", None)
    assert error_payload(ASRError("local_vad_result_invalid", unknown=True)) == ("unknown", None)


@pytest.mark.parametrize(
    "code",
    [
        "local_vad_result_invalid",
        "local_asr_empty_for_speech",
        "local_speech_segment_too_short",
        "local_emotion_result_invalid",
        "local_speaker_result_invalid",
    ],
)
def test_observation_failure_allowlist(code):
    assert safe_code(ASRError(code)) == code


@pytest.mark.parametrize(
    "error,unknown,expected_status,expected_reason,expected_error",
    [
        (
            ASRHandlerFailed("local_vad_result_invalid"),
            False,
            "failed",
            "local_vad_result_invalid",
            "stage_failed",
        ),
        (ASRHandlerFailed("private=/secret"), False, "failed", "worker_failed", "stage_failed"),
        (
            ASRHandlerFailed("local_asr_empty_for_speech"),
            True,
            "failed",
            "call_result_unknown",
            "call_result_unknown",
        ),
        (
            StopUnconfirmed(),
            False,
            "failed",
            "execution_stop_unconfirmed",
            "execution_stop_unconfirmed",
        ),
        (StopUnconfirmed(), True, "failed", "call_result_unknown", "call_result_unknown"),
        (Canceled(), False, "canceled", "cancel_confirmed", None),
        (Canceled(), True, "failed", "call_result_unknown", "call_result_unknown"),
    ],
)
def test_job_runner_persists_diagnostic_without_overriding_terminal_safety(
    monkeypatch, error, unknown, expected_status, expected_reason, expected_error
):
    job = SimpleNamespace(current_stage=None, revision=0, cancel_requested=False, attempt=1)
    stage = SimpleNamespace(id=uuid4(), status="pending", name="asr", handler="fixture")

    class Database:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, *args):
            return stage

        def commit(self):
            pass

    def fail(*args):
        raise error

    monkeypatch.setattr(job_runner, "Session", lambda _: Database())
    monkeypatch.setattr(job_runner, "claim", lambda *args: "token")
    monkeypatch.setattr(
        job_runner, "Context", lambda *args: SimpleNamespace(heartbeat=lambda: None)
    )
    monkeypatch.setattr(job_runner, "locked", lambda *args: job)
    monkeypatch.setattr(job_runner, "stages_for", lambda *args: [stage])
    monkeypatch.setattr(job_runner, "unknown_calls", lambda *args: unknown)
    monkeypatch.setattr(job_runner, "execute_handler", fail)
    job_runner.run_job(None, SimpleNamespace(job_lease_seconds=10), uuid4(), 1)
    assert job.status == expected_status and stage.reason == expected_reason
    assert (job.error["code"] if job.error else None) == expected_error
    assert job.lease_token is None and job.lease_until is None


@pytest.mark.parametrize("stop_confirmed", [True, False])
def test_parent_process_decodes_diagnostic_but_stop_failure_takes_precedence(
    monkeypatch, stop_confirmed
):
    from live_review.workers import asr_stop

    factory = multiprocessing.get_context("spawn")

    class SyntheticFactory:
        Pipe = staticmethod(factory.Pipe)

        @staticmethod
        def Process(*, target, args):
            return factory.Process(
                target=synthetic_child, args=(args[0], args[1], "local_vad_result_invalid")
            )

    def confirm():
        if not stop_confirmed:
            raise RuntimeError("private stop detail")

    monkeypatch.setattr(
        handler_process.multiprocessing, "get_context", lambda _: SyntheticFactory()
    )
    monkeypatch.setattr(asr_stop, "stop_guard", lambda *args: confirm)
    context = SimpleNamespace(
        job_id=uuid4(), token=uuid4(), stage_id=uuid4(), heartbeat=lambda **kwargs: None
    )
    settings = SimpleNamespace(job_lease_seconds=10, job_test_handlers=False)
    with pytest.raises(ASRHandlerFailed if stop_confirmed else StopUnconfirmed) as error:
        handler_process.execute_handler(context, settings, "fixture")
    if stop_confirmed:
        assert error.value.code == "local_vad_result_invalid"
    assert "private stop detail" not in str(error.value)
