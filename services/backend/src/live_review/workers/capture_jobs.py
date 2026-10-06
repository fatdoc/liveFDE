"""Existing durable jobs own process lifetime, cancellation, leases and outbox delivery."""

import json
from contextlib import nullcontext
from uuid import UUID

from sqlalchemy.orm import Session

from live_review.integrations.capture.contracts import CaptureError, StopCapture
from live_review.integrations.capture.policy import fingerprint, load_policy, require_enabled
from live_review.integrations.capture.providers import CaptureRegistry
from live_review.integrations.capture.recording import atomic_json, record
from live_review.modules.capture.files import directory, exclusive
from live_review.modules.capture.ingestion import safe_import
from live_review.modules.capture.models import CaptureRun
from live_review.modules.identity.models import Admin
from live_review.modules.jobs.execution import locked
from live_review.modules.jobs.service import now


def run_stage(context, settings, handler):
    policy = load_policy(settings)
    require_enabled(policy)
    data = context.input_data()
    if data.get("policy_sha256") != fingerprint(policy):
        raise CaptureError("capture_config_changed")
    run_id = UUID(data["capture_run_id"])

    def update(**values):
        with Session(context.engine) as db:
            locked(db, context.job_id, context.token)
            current = db.get(CaptureRun, run_id)
            for key, value in values.items():
                setattr(current, key, value)
            db.commit()

    def tick():
        context.heartbeat()
        with Session(context.engine) as db:
            current = db.get(CaptureRun, run_id)
            if current.stop_requested:
                raise StopCapture
            current.heartbeat_at = now()
            db.commit()

    with Session(context.engine, expire_on_commit=False) as db:
        run = db.get(CaptureRun, run_id)
        if not run or run.job_id != context.job_id:
            raise CaptureError("capture_job_mismatch")
        if handler == "capture.import":
            if run.state == "stopped" and not run.manifest:
                return {"stopped_without_media": True}
            admin = db.get(Admin, run.actor_id)
            return safe_import(db, admin, run, settings, policy, context.heartbeat)
        reference, platform = run.source_ref, run.platform
    path = directory(policy, run_id)
    try:
        with exclusive(path / "record.lock"):
            if (path / "manifest.json").is_file():
                manifest = json.loads((path / "manifest.json").read_text())
                update(manifest=manifest, state="recorded", active=False)
                return {"capture_run_id": str(run_id), "closed": True}
            if (path / "started.json").exists():
                raise CaptureError("restart_interrupted")
            tick()
            provider = CaptureRegistry(policy).get(platform)
            update(state="waiting_for_cast" if platform == "wechat" else "probing")
            # A receiver has one owner across all workspaces on this host.
            receiver_lock = (
                exclusive(policy.root / "finder.lock") if platform == "wechat" else nullcontext()
            )
            with receiver_lock:
                source = provider.acquire(reference, tick)
                if not source.live:
                    raise CaptureError("not_live")
                update(state="url_received")
                manifest = record(
                    source,
                    path,
                    policy,
                    tick,
                    lambda state: update(state=state),
                    platform,
                    run_id,
                    reference,
                )
            if platform == "douyin" and manifest["end_reason"] == "source_eof_unconfirmed":
                try:
                    if not provider.probe(reference, context.heartbeat).live:
                        manifest["end_reason"], manifest["complete"] = "live_ended", True
                        atomic_json(path / "manifest.json", manifest)
                except CaptureError:
                    pass  # Unknown source state must remain interrupted, not live-ended.
            update(manifest=manifest, state="recorded", active=False)
            return {"capture_run_id": str(run_id), "closed": True}
    except StopCapture:
        update(state="stopped", active=False)
        return {"stopped_without_media": True}
    except CaptureError as exc:
        update(error_code=exc.code, state="failed", active=False)
        raise
