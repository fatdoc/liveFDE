"""Real isolated RabbitMQ publish confirmation and persistent message envelope."""

from jobs_fixture import jobs as jobs
from kombu import Connection, Exchange, Queue
from sqlalchemy import select
from sqlalchemy.orm import Session

from live_review.modules.jobs.models import Outbox
from live_review.workers.dispatcher import dispatch_once
from live_review.workers.job_runner import run_job


def test_real_persistent_publish_and_duplicate_delivery(jobs):
    client, _, _, make, engine, settings = jobs
    uid = make()
    assert dispatch_once(engine, settings)
    with Session(engine) as db:
        event = db.scalar(select(Outbox).where(Outbox.job_id == uid))
        assert event.status == "sent" and event.sent_at is not None
    with Connection(settings.broker_url.get_secret_value(), connect_timeout=3) as connection:
        queue = Queue(
            "live_review",
            Exchange("live_review", type="direct", durable=True),
            routing_key="live_review",
            durable=True,
        )(connection)
        message = None
        for _ in range(30):
            candidate = queue.get(no_ack=False)
            if candidate is None:
                continue
            if candidate.payload[0][0] == str(uid):
                message = candidate
                break
            candidate.ack()  # Only this test's private BE vhost.
        assert message is not None
        assert message.properties["delivery_mode"] == 2
        assert message.payload[0] == [str(uid), 1]
        run_job(engine, settings, *message.payload[0])
        before = client.get(f"/api/v1/jobs/{uid}").json()
        run_job(engine, settings, *message.payload[0])
        assert client.get(f"/api/v1/jobs/{uid}").json() == before
        assert before["status"] == "succeeded"
        message.ack()
