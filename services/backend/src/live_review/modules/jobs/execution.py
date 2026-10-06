from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from live_review.modules.jobs.models import CallIntent, Job, Outbox
from live_review.modules.jobs.service import now, safe_error, stages_for, unknown_calls


class LostLease(Exception):
    pass


class Canceled(Exception):
    pass


class UnknownCall(Exception):
    pass


class SkipStage(Exception):
    def __init__(self, reason):
        import re

        if not isinstance(reason, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", reason):
            raise ValueError("Skip reason must be a safe reason code")
        self.reason = reason


def locked(db, job_id, token):
    job = db.scalar(
        select(Job)
        .where(Job.id == job_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not job or job.lease_token != token or not job.lease_until or job.lease_until <= now():
        raise LostLease
    return job


def claim(engine, job_id, attempt, lease_seconds):
    with Session(engine, expire_on_commit=False) as db:
        job = db.scalar(
            select(Job)
            .where(Job.id == job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            not job
            or job.attempt != attempt
            or job.status not in {"queued", "cancel_requested"}
            or job.lease_token
        ):
            return None
        if job.cancel_requested:
            job.status = "canceled"
            job.revision += 1
            for stage in stages_for(db, job.id):
                if stage.status not in {"succeeded", "skipped"}:
                    stage.status = "canceled"
            db.commit()
            return None
        token = uuid4()
        job.status, job.lease_token = "running", token
        job.lease_until = now() + timedelta(seconds=lease_seconds)
        job.revision += 1
        db.commit()
        return token


def recover_expired(engine):
    count = 0
    with Session(engine) as db:
        jobs = db.scalars(
            select(Job)
            .where(Job.lease_token.is_not(None), Job.lease_until <= now())
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        ).all()
        for job in jobs:
            stages = stages_for(db, job.id)
            if unknown_calls(db, job.id):
                job.status, job.error = (
                    "failed",
                    safe_error("call_result_unknown", "调用结果未知，需要核验，不能自动重试"),
                )
                for intent in db.scalars(
                    select(CallIntent).where(
                        CallIntent.job_id == job.id, CallIntent.state == "intent"
                    )
                ):
                    intent.state = "unknown"
                for stage in stages:
                    if stage.status == "running":
                        stage.status, stage.reason = "failed", "call_result_unknown"
            elif job.input_data.get("kind") == "asr_stream_v1":
                job.status, job.error = "failed", safe_error(
                    "stream_not_replayable", "实时音频未持久保存，不能自动重放"
                )
                for stage in stages:
                    if stage.status not in {"succeeded", "skipped"}:
                        stage.status, stage.reason = "failed", "stream_not_replayable"
            elif job.cancel_requested or job.input_data.get("kind") == "asr_gateway_v1":
                job.status = "failed"
                job.error = safe_error(
                    "execution_stop_unconfirmed", "执行进程中断，停止状态需要核验"
                )
                for stage in stages:
                    if stage.status not in {"succeeded", "skipped"}:
                        stage.status, stage.reason = "failed", "execution_stop_unconfirmed"
            else:
                job.status = "queued"
                for stage in stages:
                    if stage.status == "running":
                        stage.status = "pending"
                db.add(Outbox(job_id=job.id, attempt=job.attempt, next_attempt_at=now()))
            job.lease_token, job.lease_until = None, None
            job.revision += 1
            count += 1
        db.commit()
    return count


class Context:
    def __init__(self, engine, job_id, token, stage_id, lease_seconds):
        self.engine, self.job_id, self.token = engine, job_id, token
        self.stage_id, self.lease_seconds = stage_id, lease_seconds

    def heartbeat(self, renew=True):
        with Session(self.engine) as db:
            job = locked(db, self.job_id, self.token)
            if job.cancel_requested:
                raise Canceled
            if renew:
                job.lease_until = now() + timedelta(seconds=self.lease_seconds)
            db.commit()

    def input_data(self):
        with Session(self.engine) as db:
            return locked(db, self.job_id, self.token).input_data

    def begin_paid_call(self, call_key):
        if not call_key or len(call_key) > 128:
            raise ValueError("Invalid call key")
        with Session(self.engine, expire_on_commit=False) as db:
            job = locked(db, self.job_id, self.token)
            if job.cancel_requested:
                raise Canceled
            previous = db.scalar(
                select(CallIntent)
                .where(
                    CallIntent.job_id == job.id,
                    CallIntent.stage_id == self.stage_id,
                    CallIntent.call_key == call_key,
                )
                .order_by(CallIntent.attempt.desc())
                .limit(1)
            )
            if previous:
                if previous.state != "known":
                    raise UnknownCall
                return {"intent_id": previous.id, "execute": False, "result": previous.result}
            intent = CallIntent(
                job_id=job.id,
                stage_id=self.stage_id,
                attempt=job.attempt,
                call_key=call_key,
                state="intent",
            )
            db.add(intent)
            db.commit()
            return {"intent_id": intent.id, "execute": True, "result": None}

    def finish_paid_call(self, intent_id, result):
        with Session(self.engine) as db:
            locked(db, self.job_id, self.token)
            intent = db.scalar(
                select(CallIntent)
                .where(
                    CallIntent.id == intent_id,
                    CallIntent.job_id == self.job_id,
                    CallIntent.stage_id == self.stage_id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if not intent or intent.state != "intent":
                raise UnknownCall
            intent.state, intent.result = "known", result
            db.commit()
