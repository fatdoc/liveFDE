"""One resident configuration per process, bounded by explicit idle eviction."""

import asyncio
import hashlib
import os
import threading
import time
from contextlib import asynccontextmanager

from ..contracts import ASRError
from .locking import acquire_file_lock
from .models import Models

_guard = threading.Lock()
_entry = None
_timer = None
_generation = 0


def _fingerprint(config):
    canonical = config.model_copy(update={"model_root": config.model_root.resolve()})
    return hashlib.sha256(canonical.model_dump_json().encode()).hexdigest()


def _drop():
    global _entry
    if _entry is not None:
        try:
            _entry[1].clear()
        finally:
            os.close(_entry[2])
            _entry = None


def _expire(generation):
    if not _guard.acquire(blocking=False):
        return  # active request schedules its own fresh idle timer when it finishes
    try:
        if _entry is not None and _generation == generation:
            _drop()
    finally:
        _guard.release()


async def _acquire_guard(timeout):
    deadline = time.monotonic() + timeout
    while not _guard.acquire(blocking=False):
        if time.monotonic() >= deadline:
            raise ASRError("local_model_busy")
        await asyncio.sleep(0.05)


async def unload_local_models():
    """Explicit graceful shutdown hook; never unloads during live inference."""
    global _timer
    await _acquire_guard(3600)
    try:
        if _timer is not None:
            _timer.cancel()
            _timer = None
        _drop()
    finally:
        _guard.release()


@asynccontextmanager
async def model_lease(config):
    global _entry, _timer, _generation
    key = _fingerprint(config)
    await _acquire_guard(config.lock_timeout_seconds)
    try:
        _generation += 1
        if _timer is not None:
            _timer.cancel()
            _timer = None
        if _entry is None or _entry[0] != key:
            _drop()
            fd = await acquire_file_lock(config.model_root.resolve(), config.lock_timeout_seconds)
            _entry = (key, Models(config), fd)
        try:
            yield _entry[1]
        except BaseException:
            # Failed/cancelled inference does not leave questionable model state resident.
            _drop()
            raise
    finally:
        if _entry is not None:
            _timer = threading.Timer(config.cache_idle_seconds, _expire, args=(_generation,))
            _timer.daemon = True
            _timer.start()
        _guard.release()
