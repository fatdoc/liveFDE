from celery import Celery

from live_review.core.config import get_settings

celery_app = Celery("live_review", broker=get_settings().broker_url.get_secret_value())
celery_app.conf.update(
    task_default_queue="live_review",
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
    worker_pool="solo",
    imports=["live_review.workers.tasks"],
    broker_transport_options={"confirm_publish": True},
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_delivery_mode="persistent",
)
