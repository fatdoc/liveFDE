import json
from uuid import UUID

from sqlalchemy.orm import Session

from live_review.modules.jobs.execution import (
    Canceled,
    Context,
    LostLease,
    SkipStage,
    UnknownCall,
    claim,
    locked,
)
from live_review.modules.jobs.models import JobStage
from live_review.modules.jobs.service import safe_error, stages_for, unknown_calls
from live_review.workers.handler_process import ASRHandlerFailed, StopUnconfirmed, execute_handler
from live_review.workers.handlers import HandlerUnavailable


def run_job(engine, settings, job_id, attempt):
    job_id = UUID(str(job_id))
    token = claim(engine, job_id, attempt, settings.job_lease_seconds)
    if token is None:
        return
    try:
        with Session(engine) as db:
            stage_ids = [
                s.id for s in stages_for(db, job_id) if s.status not in {"succeeded", "skipped"}
            ]
        for stage_id in stage_ids:
            context = Context(engine, job_id, token, stage_id, settings.job_lease_seconds)
            context.heartbeat()
            with Session(engine) as db:
                job = locked(db, job_id, token)
                stage = db.get(JobStage, stage_id)
                stage.status = "running"
                job.current_stage = stage.name
                job.revision += 1
                handler_name = stage.handler
                db.commit()
            skip_reason = None
            try:
                artifact = execute_handler(context, settings, handler_name)
                if (
                    not isinstance(artifact, dict)
                    or len(json.dumps(artifact, allow_nan=False)) > 262144
                ):
                    raise ValueError("Invalid stage artifact")
            except SkipStage as skip:
                artifact, skip_reason = None, skip.reason
            with Session(engine) as db:
                job = locked(db, job_id, token)
                if unknown_calls(db, job_id):
                    raise UnknownCall
                if job.cancel_requested:
                    raise Canceled
                stage = db.get(JobStage, stage_id)
                stage.artifact, stage.status, stage.reason = (
                    artifact,
                    "skipped" if skip_reason else "succeeded",
                    skip_reason,
                )
                stage.completed_attempt = job.attempt
                job.revision += 1
                db.commit()
        with Session(engine) as db:
            job = locked(db, job_id, token)
            if job.cancel_requested:
                raise Canceled
            job.status = "succeeded"
            job.revision += 1
            job.lease_token, job.lease_until = None, None
            db.commit()
    except LostLease:
        return
    except Exception as error:
        try:
            with Session(engine) as db:
                job = locked(db, job_id, token)
                unknown = unknown_calls(db, job_id)
                canceled = isinstance(error, Canceled) and not unknown
                code = (
                    "call_result_unknown"
                    if unknown
                    else (
                        "execution_stop_unconfirmed"
                        if isinstance(error, StopUnconfirmed)
                        else (
                            "handler_unavailable"
                            if isinstance(error, HandlerUnavailable)
                            else "stage_failed"
                        )
                    )
                )
                job.status = "canceled" if canceled else "failed"
                job.error = None if canceled else safe_error(code, "任务未完成，请查看阶段状态")
                for stage in stages_for(db, job_id):
                    if stage.status == "running" or (canceled and stage.status == "pending"):
                        stage.status = "canceled" if canceled else "failed"
                        stage.reason = (
                            "cancel_confirmed"
                            if canceled
                            else error.code
                            if code == "stage_failed" and isinstance(error, ASRHandlerFailed)
                            else code
                        )
                job.revision += 1
                job.lease_token, job.lease_until = None, None
                db.commit()
        except LostLease:
            pass
