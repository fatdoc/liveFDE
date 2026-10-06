from live_review.core.config import get_settings
from live_review.core.database import build_engine
from live_review.workers.celery_app import celery_app
from live_review.workers.job_runner import run_job


@celery_app.task(name="live_review.run_job", acks_late=True, reject_on_worker_lost=True)
def execute(job_id, attempt):
    settings = get_settings()
    engine = build_engine(settings)
    try:
        run_job(engine, settings, job_id, attempt)
    finally:
        engine.dispose()
