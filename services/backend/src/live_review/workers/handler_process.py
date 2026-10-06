"""Handler process boundary: cancellation joins the child before terminal state."""

import multiprocessing
import os
import signal
import threading
import time

from live_review.core.database import build_engine
from live_review.integrations.asr_gateway.contracts import ASRError
from live_review.integrations.asr_gateway.local_worker.protocol import safe_code
from live_review.modules.jobs.execution import Canceled, Context, LostLease, SkipStage, UnknownCall
from live_review.workers.handlers import HandlerUnavailable, resolve


class StopUnconfirmed(Exception):
    """Execution may still be alive; automatic replay is forbidden."""


class ASRHandlerFailed(Exception):
    """Only a sanitized diagnostic crosses the private handler pipe."""

    def __init__(self, code):
        self.code = safe_code(ASRError(code))
        super().__init__(self.code)


def error_payload(error):
    # Control-flow categories take precedence over optional diagnostics.
    if isinstance(error, LostLease):
        return "lost", None
    if isinstance(error, Canceled):
        return "canceled", None
    if isinstance(error, UnknownCall):
        return "unknown", None
    if isinstance(error, HandlerUnavailable):
        return "unavailable", None
    if isinstance(error, ASRError):
        if error.unknown:
            return "unknown", None
        return "asr_failed", safe_code(error)
    return "failed", None


def _child(connection, parent_pid, settings, job_id, token, stage_id, handler_name):
    os.setsid()

    # The private pipe is held only by this worker and its child. EOF or missed
    # heartbeats terminate the child even if the worker is SIGKILLed or paused.
    def watch_parent():
        last = time.monotonic()
        while True:
            try:
                if connection.poll(0.05):
                    if connection.recv() == "alive":
                        last = time.monotonic()
            except (EOFError, OSError):
                os.killpg(os.getpid(), signal.SIGKILL)
            if os.getppid() != parent_pid or time.monotonic() - last > settings.job_lease_seconds:
                os.killpg(os.getpid(), signal.SIGKILL)

    threading.Thread(target=watch_parent, daemon=True).start()
    engine = build_engine(settings)
    try:
        context = Context(engine, job_id, token, stage_id, settings.job_lease_seconds)
        artifact = resolve(handler_name, settings)(context)
        connection.send(("ok", artifact))
    except SkipStage as skip:
        connection.send(("skip", skip.reason))
    except BaseException as error:
        category, diagnostic = error_payload(error)
        print(f"handler_error code={diagnostic or category}", flush=True)
        connection.send((category, diagnostic))
    finally:
        engine.dispose()
        connection.close()


def execute_handler(context, settings, handler_name):
    from live_review.workers.asr_stop import stop_guard

    confirm_stop = stop_guard(context, settings, handler_name)
    completed = False
    factory = multiprocessing.get_context("spawn")
    parent, child = factory.Pipe()
    process = factory.Process(
        target=_child,
        args=(
            child,
            os.getpid(),
            settings,
            context.job_id,
            context.token,
            context.stage_id,
            handler_name,
        ),
    )
    process.start()
    child.close()
    print(f"handler_started job={context.job_id} pid={process.pid}", flush=True)
    no_renew = settings.job_test_handlers and handler_name == "fixture.no_heartbeat"
    last_renew = time.monotonic()
    parent.send("alive")
    try:
        while True:
            if not no_renew or time.monotonic() - last_renew < settings.job_lease_seconds:
                # Every poll verifies cancellation and fencing; renewal is bounded.
                context.heartbeat(renew=not no_renew)
            else:
                raise LostLease
            if not no_renew:
                try:
                    parent.send("alive")
                except BrokenPipeError:
                    pass  # Completed child may have closed its end after sending result.
            if parent.poll(0.1):
                try:
                    category, artifact = parent.recv()
                except EOFError as error:
                    raise RuntimeError("Handler process exited") from error
                process.join(timeout=2)
                if process.is_alive():
                    raise RuntimeError("Handler did not stop after result")
                if category == "ok":
                    completed = True
                    return artifact
                if category == "skip":
                    raise SkipStage(artifact)
                if category == "asr_failed":
                    raise ASRHandlerFailed(artifact)
                kinds = {
                    "lost": LostLease,
                    "canceled": Canceled,
                    "unknown": UnknownCall,
                    "unavailable": HandlerUnavailable,
                }
                raise kinds.get(category, RuntimeError)()
            if not process.is_alive():
                raise RuntimeError("Handler process exited")
    finally:
        if process.is_alive():
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                process.terminate()
            process.join(timeout=2)
        if process.is_alive():
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                process.kill()
            process.join(timeout=5)
        parent.close()
        if process.is_alive():
            raise StopUnconfirmed
        if confirm_stop is not None and not completed:
            try:
                confirm_stop()
            except Exception:
                raise StopUnconfirmed from None
        print(f"handler_stopped job={context.job_id} pid={process.pid}", flush=True)
