"""Private runtime layout and process locks; no API supplied paths."""

import fcntl
import os
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from live_review.integrations.capture.contracts import CaptureError


def directory(policy, run_id):
    root = Path(policy.root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.resolve() != root:
        raise CaptureError("unsafe_capture_root")
    os.chmod(root, 0o700)
    path = root / str(UUID(str(run_id)))
    path.mkdir(exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise CaptureError("unsafe_capture_path")
    return path


@contextmanager
def exclusive(path):
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise CaptureError("capture_busy") from None
        yield
    finally:
        os.close(descriptor)


def load_manifest(path):
    import stat

    from pydantic import ValidationError

    from live_review.integrations.capture.contracts import CaptureManifest

    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor) as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
                raise CaptureError("invalid_manifest")
            return CaptureManifest.model_validate_json(stream.read(65537)).model_dump(mode="json")
    except FileNotFoundError:
        raise CaptureError("capture_not_closed") from None
    except (OSError, ValueError, ValidationError):
        raise CaptureError("invalid_manifest") from None
