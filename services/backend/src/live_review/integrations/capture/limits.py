"""Per-run limits and two-volume capacity, independent of credential/provider configuration."""

import shutil
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from live_review.integrations.capture.contracts import CaptureError

GIB = 1024**3
OVERRUN_BYTES = 64 * 1024**2


class RecordingLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    max_seconds: int = Field(ge=1, le=14400)
    max_bytes: int = Field(ge=1048576, le=16 * GIB)
    min_free_bytes: int = Field(ge=1048576)


def select_limits(policy, duration=None, maximum=None):
    values = RecordingLimits(
        max_seconds=duration
        if duration is not None
        else min(policy.default_duration_seconds, policy.max_seconds),
        max_bytes=maximum
        if maximum is not None
        else min(policy.default_max_bytes, policy.max_bytes),
        min_free_bytes=policy.min_free_bytes,
    )
    return validate_limits(policy, values.model_dump())


def validate_limits(policy, data):
    try:
        values = RecordingLimits.model_validate(data)
        if (
            values.max_seconds > policy.max_seconds
            or values.max_bytes > policy.max_bytes
            or values.min_free_bytes != policy.min_free_bytes
        ):
            raise ValueError
        return values
    except ValueError:
        raise CaptureError("invalid_recording_limits") from None


def effective_policy(policy, data):
    if "recording_limits" not in data:  # Existing jobs keep their original policy behavior.
        return policy
    return policy.model_copy(update=validate_limits(policy, data["recording_limits"]).model_dump())


def disk(path):
    if path is None:
        raise CaptureError("capture_storage_unavailable")
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise CaptureError("capture_storage_unavailable")
    while not path.exists():
        path = path.parent
    try:
        return path.stat().st_dev, shutil.disk_usage(path).free
    except OSError:
        raise CaptureError("capture_storage_unavailable") from None


def available_bytes(capture_root, storage_root, reserve):
    first, second = disk(capture_root), disk(storage_root)
    if first[0] == second[0]:
        return max(0, (min(first[1], second[1]) - reserve) // 3 - OVERRUN_BYTES)
    return max(0, min(first[1] - reserve, (second[1] - reserve) // 2) - OVERRUN_BYTES)


def require_capacity(capture_root, storage_root, reserve, size, *, before_start=False):
    if before_start:
        safe = available_bytes(capture_root, storage_root, reserve) >= size
    else:
        first, second = disk(capture_root), disk(storage_root)
        safe = (
            min(first[1], second[1]) >= reserve + 2 * size + 3 * OVERRUN_BYTES
            if first[0] == second[0]
            else first[1] >= reserve + OVERRUN_BYTES
            and second[1] >= reserve + 2 * (size + OVERRUN_BYTES)
        )
    if not safe:
        raise CaptureError("disk_full")


def health_limits(policy, settings):
    try:
        available = min(
            policy.max_bytes,
            available_bytes(policy.root, settings.storage_root, policy.min_free_bytes),
        )
    except CaptureError:
        available = None
    defaults = select_limits(policy)
    return {
        "max_seconds": policy.max_seconds,
        "max_bytes": policy.max_bytes,
        "default_duration_seconds": defaults.max_seconds,
        "default_max_bytes": defaults.max_bytes,
        "duration_presets_seconds": [
            n for n in (1800, 3600, 7200, 14400) if n <= policy.max_seconds
        ],
        "min_free_bytes": policy.min_free_bytes,
        "manual_upload_max_bytes": settings.upload_max_bytes,
        "available_max_bytes": available,
        "import_overhead_copies": 2,
        "fragmented_mp4": True,
        "resumable_recording": False,
        "size_overrun_bytes": OVERRUN_BYTES,
    }
