"""Job-scoped, immutable JSON artifacts; database stage outputs contain only references."""

import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from live_review.integrations.media.process import MediaError


def controlled(root: Path, relative: str) -> Path:
    if not root.is_absolute() or root.resolve() != root:
        raise MediaError("artifact_root_invalid")
    candidate = root / relative
    if (
        Path(relative).is_absolute()
        or candidate.resolve() != candidate
        or (not candidate.is_relative_to(root) or ".." in Path(relative).parts)
    ):
        raise MediaError("artifact_path_invalid")
    return candidate


def write_json(root: Path, directory: str, payload: dict) -> dict:
    path = controlled(root, f"{directory}/{uuid4()}.json")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    content = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
    if len(content) > 8 * 1024 * 1024:
        raise MediaError("artifact_too_large")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    return {
        "artifact_ref": str(path.relative_to(root)),
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
    }


def read_json(root: Path, reference: dict) -> dict:
    path = controlled(root, reference["artifact_ref"])
    with path.open("rb") as stream:
        content = stream.read(8 * 1024 * 1024 + 1)
    if (
        len(content) != reference["size_bytes"]
        or len(content) > 8 * 1024 * 1024
        or (hashlib.sha256(content).hexdigest() != reference["sha256"])
    ):
        raise MediaError("artifact_integrity_invalid")
    return json.loads(content)
