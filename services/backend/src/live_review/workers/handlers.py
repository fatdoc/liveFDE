"""Explicit registry. No dynamic imports from job payload and no production fake results."""

import time

from live_review.modules.jobs.execution import UnknownCall


class HandlerUnavailable(Exception):
    pass


def resolve(name, settings):
    if name == "asr.gateway":
        from live_review.workers.asr_jobs import run_stage

        return lambda context: run_stage(context, settings)
    if name in {"media.extract", "media.asr"}:
        from live_review.workers.media_jobs import run_stage

        return lambda context: run_stage(context, settings, name)
    if settings.job_test_handlers and settings.environment != "production":
        handlers = {
            "fixture.echo": echo,
            "fixture.skip": skip,
            "fixture.fail": fail,
            "fixture.slow": slow,
            "fixture.unknown": unknown,
            "fixture.known": known,
            "fixture.fail_once": fail_once,
            "fixture.paid_unknown": paid_unknown,
            "fixture.no_heartbeat": no_heartbeat,
            "fixture.uncooperative": no_heartbeat,
        }
        if name in handlers:
            return handlers[name]
    raise HandlerUnavailable


def echo(context):
    context.heartbeat()
    return {"synthetic": True, "value": context.input_data().get("value")}


def fail(context):
    raise ValueError("synthetic failure: must never expose this raw text")


def slow(context):
    duration = min(float(context.input_data().get("delay_seconds", 2)), 60)
    end = time.monotonic() + duration
    while time.monotonic() < end:
        context.heartbeat()
        time.sleep(0.1)
    return {"synthetic": True, "waited": duration}


def unknown(context):
    context.begin_paid_call("synthetic-provider-call")
    # No model/service invoked. Simulates loss of knowledge after durable intent.
    raise UnknownCall


def known(context):
    call = context.begin_paid_call("synthetic-known-call")
    if call["execute"]:
        context.finish_paid_call(call["intent_id"], {"synthetic": True, "cached": True})
    return {"synthetic": True, "cached": True}


def fail_once(context):
    from sqlalchemy.orm import Session

    from live_review.modules.jobs.execution import locked

    with Session(context.engine) as db:
        if locked(db, context.job_id, context.token).attempt == 1:
            raise ValueError("synthetic first-attempt failure")
    return {"synthetic": True, "retried": True}


def paid_unknown(context):
    context.begin_paid_call("synthetic-provider-call")
    end = time.monotonic() + min(float(context.input_data().get("delay_seconds", 30)), 120)
    while time.monotonic() < end:
        context.heartbeat()
        time.sleep(0.1)
    raise UnknownCall


def no_heartbeat(context):
    time.sleep(min(float(context.input_data().get("delay_seconds", 3)), 120))
    return {"synthetic": True, "expired": True}


def skip(context):
    from live_review.modules.jobs.execution import SkipStage

    raise SkipStage("not_applicable")
