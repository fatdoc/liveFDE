"""Bounded local JSON-lines protocol; paths/configuration never become error messages."""

import hashlib
import json
import os
import stat
from pathlib import Path

from ..contracts import ASRError

MAX_FRAME = 128 * 1024
MAX_CHUNK = 64 * 1024
SAFE_CODES = frozenset(
    {
        "worker_canceled",
        "worker_stop_unconfirmed",
        "worker_request_reused",
        "worker_request_id_invalid",
        "worker_protocol_invalid",
        "worker_config_mismatch",
        "worker_path_rejected",
        "worker_local_only_required",
        "worker_pcm_invalid",
        "worker_duration_exceeded",
        "worker_input_idle",
        "worker_busy",
        "worker_unavailable",
        "worker_timeout",
        "worker_failed",
        "worker_response_invalid",
        "worker_socket_invalid",
        "worker_backpressure",
        "local_model_busy",
        "local_inference_failed",
        "local_device_out_of_memory",
        "local_timeout",
        "local_dependencies_missing",
        "local_model_missing",
        "local_cuda_unavailable",
        "local_mps_unsupported",
        "local_language_unsupported",
        "local_audio_requires_16k_mono",
        "audio_duration_exceeded",
        "audio_empty_or_too_short",
    }
)


def safe_code(error):
    value = getattr(error, "code", None)
    return value if isinstance(value, str) and value in SAFE_CODES else "worker_failed"


def fingerprint(config):
    values = config.model_dump(mode="json")
    values["model_root"] = str(Path(values["model_root"]).resolve())
    return hashlib.sha256(
        json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def socket_path(path, *, existing):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise ASRError("worker_socket_invalid")
    parent = path.parent.stat()
    if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
        raise ASRError("worker_socket_invalid")
    if existing:
        info = path.lstat()
        if (
            not stat.S_ISSOCK(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise ASRError("worker_socket_invalid")
    elif path.exists() or path.is_symlink():
        raise ASRError("worker_socket_invalid")
    return path


async def read(reader):
    try:
        raw = await reader.readline()
        if not raw:
            raise EOFError
        if len(raw) > MAX_FRAME or not raw.endswith(b"\n"):
            raise ValueError
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (ValueError, UnicodeError):
        raise ASRError("worker_protocol_invalid") from None


async def write(writer, value):
    try:
        raw = json.dumps(value, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    except (ValueError, TypeError):
        raise ASRError("worker_protocol_invalid") from None
    if len(raw) > MAX_FRAME:
        raise ASRError("worker_protocol_invalid")
    writer.write(raw)
    await writer.drain()
