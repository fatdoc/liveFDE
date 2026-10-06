"""Local executor liveness, bound to the database and exact capture policy.

This is a same-host runtime heartbeat, not a task store. Durable work remains in
jobs/outbox. A fresh file alone is insufficient: the process lock must be held.
"""

import fcntl
import hashlib
import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path

from live_review.integrations.capture.policy import fingerprint

HEARTBEAT_TTL = 10


def binding(settings, policy):
    return hashlib.sha256(
        (settings.database_url.get_secret_value() + "\n" + fingerprint(policy)).encode()
    ).hexdigest()


def paths(policy):
    root = Path(policy.root)
    return root / ".executor.lock", root / ".executor.json"


def execution_health(settings, policy):
    result = {
        "mode": policy.execution_mode,
        "automatic_dispatch": policy.execution_mode == "native",
        "ready": False,
        "state": "unavailable",
        "reason": "capture_executor_unavailable",
        "heartbeat_at": None,
    }
    if not policy.enabled or not policy.root:
        return result | {"state": "disabled", "reason": "capture_not_configured"}
    if policy.execution_mode != "native":
        return result | {"state": "manual", "reason": "capture_manual_execution"}
    lock_path, heartbeat_path = paths(policy)
    try:
        descriptor = os.open(heartbeat_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor) as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 4096:
                return result
            stamp = json.load(stream)
        if stamp.get("binding") != binding(settings, policy):
            return result | {"reason": "capture_executor_config_mismatch"}
        timestamp = datetime.fromisoformat(stamp["heartbeat_at"])
        age = (datetime.now(UTC) - timestamp).total_seconds()
        if not -2 <= age <= HEARTBEAT_TTL:
            return result
        descriptor = os.open(lock_path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                return result
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return result
            except BlockingIOError:
                pass
        finally:
            os.close(descriptor)
        state = stamp["state"]
        if state not in {"idle", "busy", "draining"}:
            return result
        return result | {
            "ready": state in {"idle", "busy"},
            "state": state,
            "reason": None if state in {"idle", "busy"} else "capture_executor_draining",
            "heartbeat_at": timestamp,
        }
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return result
