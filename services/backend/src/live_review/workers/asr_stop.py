"""Confirm shared-worker termination after a file handler process is interrupted."""

import asyncio

from sqlalchemy.orm import Session

from live_review.integrations.asr_gateway.factory import create_provider
from live_review.modules.jobs.execution import locked
from live_review.workers.asr_jobs import restore_gateway


def stop_guard(context, settings, handler_name):
    if handler_name != "asr.gateway":
        return None
    data = context.input_data()
    if data["preferences"]["provider"] != "local":
        return None
    with Session(context.engine) as db:
        job = locked(db, context.job_id, context.token)
        attempt, workspace_id = job.attempt, job.workspace_id
    registry = restore_gateway(data, settings, workspace_id)
    provider = create_provider(registry, "local")
    request_id = f"{context.job_id}:{attempt}"

    def confirm():
        asyncio.run(provider.cancel_and_wait(request_id))

    return confirm
