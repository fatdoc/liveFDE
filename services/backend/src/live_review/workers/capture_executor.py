"""Same-host native capture consumer of the existing durable outbox.

Run once as an operator-managed service, never from an HTTP request. One native
executor owns a runtime root. Existing run_job leases fence duplicate deliveries.
"""

import argparse
import json
import os
import signal
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text, update
from sqlalchemy.orm import Session

from live_review.core.config import get_settings
from live_review.core.database import build_engine
from live_review.integrations.capture.contracts import CaptureError
from live_review.integrations.capture.policy import fingerprint, load_policy, require_enabled
from live_review.modules.capture.executor_health import binding, paths
from live_review.modules.capture.files import exclusive
from live_review.modules.capture.models import CaptureRun
from live_review.workers.dispatcher import dispatch_once
from live_review.workers.job_runner import run_job


class CaptureExecutor:
    def __init__(self, engine, settings):
        self.engine, self.settings = engine, settings
        self.policy = load_policy(settings)
        self.stop = threading.Event()
        self.finished = threading.Event()
        self.current_job = None
        self.state_lock = threading.Lock()

    def request_shutdown(self, *_):
        self.stop.set()

    def _heartbeat(self):
        # Also probe DB: a live OS process with no database is not ready to accept work.
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        current = load_policy(self.settings)
        if fingerprint(current) != fingerprint(self.policy):
            self.stop.set()
        with self.state_lock:
            job_id = self.current_job
        if self.stop.is_set() and job_id:
            with Session(self.engine) as db:
                db.execute(
                    update(CaptureRun)
                    .where(CaptureRun.job_id == job_id, CaptureRun.active.is_(True))
                    .values(stop_requested=True)
                )
                db.commit()
        state = "draining" if self.stop.is_set() else "busy" if job_id else "idle"
        _, target = paths(self.policy)
        payload = {
            "binding": binding(self.settings, self.policy),
            "heartbeat_at": datetime.now(UTC).isoformat(),
            "state": state,
        }
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=target.parent, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(payload, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

    def _pulse(self):
        while not self.finished.is_set():
            try:
                self._heartbeat()
            except Exception:
                # No exception text: database URLs or provider URLs may be sensitive.
                paths(self.policy)[1].unlink(missing_ok=True)
                print("capture_executor_heartbeat_unavailable", flush=True)
            self.finished.wait(2)

    def _execute(self, event, settings):
        if self.stop.is_set():
            raise CaptureError("capture_executor_draining")
        with self.state_lock:
            self.current_job = event.job_id
        try:
            self._heartbeat()
            if self.stop.is_set():
                raise CaptureError("capture_executor_draining")
            run_job(self.engine, settings, event.job_id, event.attempt)
        finally:
            with self.state_lock:
                self.current_job = None

    def run(self, *, once=False):
        require_enabled(self.policy)
        if self.policy.execution_mode != "native":
            raise CaptureError("capture_native_execution_not_configured")
        root = Path(self.policy.root)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if root.resolve() != root:
            raise CaptureError("unsafe_capture_root")
        os.chmod(root, 0o700)
        lock_path, heartbeat_path = paths(self.policy)
        with exclusive(lock_path):
            pulse = threading.Thread(target=self._pulse, daemon=True)
            try:
                self._heartbeat()
                pulse.start()
                while not self.stop.is_set():
                    dispatch_once(
                        self.engine, self.settings, publisher=self._execute, kind="capture_v1"
                    )
                    if once:
                        break
                    self.stop.wait(self.settings.job_dispatch_interval_seconds)
            finally:
                self.stop.set()
                self.finished.set()
                if pulse.ident:
                    pulse.join(timeout=10)
                heartbeat_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Consume at most one existing event")
    args = parser.parse_args()
    settings = get_settings()
    engine = build_engine(settings)
    executor = CaptureExecutor(engine, settings)
    signal.signal(signal.SIGTERM, executor.request_shutdown)
    signal.signal(signal.SIGINT, executor.request_shutdown)
    try:
        executor.run(once=args.once)
    except CaptureError as error:
        print(error.code, flush=True)
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
