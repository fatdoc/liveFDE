"""PostgreSQL outbox dispatcher; confirms before marking sent; safe duplicate delivery."""

import argparse
import json
import time
from datetime import timedelta

from kombu import Connection, Exchange, Queue
from sqlalchemy import select
from sqlalchemy.orm import Session

from live_review.core.config import get_settings
from live_review.core.database import build_engine
from live_review.core.health import dependencies_ready
from live_review.modules.jobs.execution import recover_expired
from live_review.modules.jobs.models import Job, Outbox
from live_review.modules.jobs.service import now
from live_review.workers.celery_app import celery_app


def publish(event, settings):
    with Connection(
        settings.broker_url.get_secret_value(),
        connect_timeout=3,
        transport_options={"confirm_publish": True, "read_timeout": 5, "write_timeout": 5},
    ) as connection:
        connection.connect()
        channel = connection.channel()
        queue = Queue(
            "live_review",
            Exchange("live_review", type="direct", durable=True),
            routing_key="live_review",
            durable=True,
            channel=channel,
        )
        queue.declare()  # Durable known queue; no silent publish to a missing binding.
        returned = []
        producer = connection.Producer(
            channel=channel, on_return=lambda *args: returned.append(True)
        )
        celery_app.send_task(
            "live_review.run_job",
            args=[str(event.job_id), event.attempt],
            task_id=str(event.id),
            producer=producer,
            queue=queue,
            delivery_mode=2,
            mandatory=True,
            retry=False,
            timeout=5,
            confirm_timeout=5,
        )
        if returned:
            raise RuntimeError("Broker returned unroutable task")


def dispatch_once(engine, settings, publisher=publish, *, kind=None):
    recover_expired(engine, kind=kind)
    with Session(engine) as db:
        query = select(Outbox).where(
            Outbox.status == "pending", Outbox.next_attempt_at <= now()
        )
        if kind is not None:
            query = query.join(Job, Job.id == Outbox.job_id).where(
                Job.input_data["kind"].astext == kind
            )
        event = db.scalar(
            query.order_by(Outbox.next_attempt_at, Outbox.id)
            .with_for_update(skip_locked=True, of=Outbox)
            .limit(1)
        )
        if event is None:
            return False
        event.delivery_attempts += 1
        try:
            publisher(event, settings)
        except Exception:
            event.next_attempt_at = now() + timedelta(
                seconds=min(60, 2 ** min(event.delivery_attempts, 5))
            )
        else:
            event.status, event.sent_at = "sent", now()
        db.commit()
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--once", action="store_true")
    group.add_argument("--check", action="store_true")
    group.add_argument("--loop", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    engine = build_engine(settings)
    try:
        if args.check:
            checks = dependencies_ready(engine, settings.broker_url.get_secret_value())
            print(json.dumps({"mode": "preflight_only", "checks": checks}))
            return 0 if all(v == "up" for v in checks.values()) else 1
        while True:
            dispatch_once(engine, settings)
            if args.once:
                return
            time.sleep(settings.job_dispatch_interval_seconds)
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
