"""Process-wide inference serialization, including weight residency."""

import asyncio
import fcntl
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from ..contracts import ASRError


async def acquire_file_lock(root: Path, timeout: float):
    fd = os.open(root / ".inference.lock", os.O_CREAT | os.O_RDWR, 0o600)
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise ASRError("local_model_busy") from None
                await asyncio.sleep(0.05)
    except BaseException:
        os.close(fd)
        raise


@asynccontextmanager
async def inference_lock(root: Path, timeout: float):
    fd = await acquire_file_lock(root, timeout)
    try:
        yield
    finally:
        os.close(fd)
