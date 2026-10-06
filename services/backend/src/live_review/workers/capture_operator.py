"""Run an already persisted capture job using the existing job runner.

Development/operator entrypoint, separate from HTTP requests. Production uses
workers.dispatcher and Celery as usual. This does not create a second queue.
"""
import argparse
from uuid import UUID

from sqlalchemy.orm import Session

from live_review.core.config import get_settings
from live_review.core.database import build_engine
from live_review.modules.capture.models import CaptureRun  # noqa: F401
from live_review.modules.jobs.execution import recover_expired
from live_review.modules.jobs.models import Job
from live_review.workers.job_runner import run_job


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_id", type=UUID)
    args = parser.parse_args()
    settings = get_settings()
    engine = build_engine(settings)
    try:
        recover_expired(engine)
        with Session(engine) as db:
            job = db.get(Job, args.job_id)
            if not job or job.input_data.get("kind") != "capture_v1":
                raise SystemExit("capture_job_not_found")
            attempt = job.attempt
        run_job(engine, settings, args.job_id, attempt)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
