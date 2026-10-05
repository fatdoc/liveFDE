from uuid import UUID

from fastapi import APIRouter, Header, Response

from live_review.core.auth import CurrentAdmin, Database, MutationAdmin
from live_review.modules.jobs.schemas import CancelInput, JobOutput, RetryInput
from live_review.modules.jobs.service import cancel_job, owned, retry_job, view

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOutput)
def get_job(job_id: UUID, admin: CurrentAdmin, db: Database):
    return view(db, owned(db, job_id, admin))


@router.post("/{job_id}/retry", status_code=202, response_model=JobOutput)
def retry(
    job_id: UUID,
    payload: RetryInput,
    admin: MutationAdmin,
    db: Database,
    idempotency_key: str = Header(default=""),
):
    return retry_job(
        db, job_id, admin, idempotency_key, payload.expected_revision, payload.from_stage
    )


@router.post("/{job_id}/cancel", status_code=202, response_model=JobOutput)
def cancel(
    job_id: UUID, payload: CancelInput, response: Response, admin: MutationAdmin, db: Database
):
    result, response.status_code = cancel_job(db, job_id, admin, payload.expected_revision)
    return result
