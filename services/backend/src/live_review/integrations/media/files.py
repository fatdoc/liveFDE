import hashlib
import os
from pathlib import Path

from live_review.integrations.media.models import Artifact
from live_review.integrations.media.process import Cancel, MediaError, check_cancel


def controlled_file(root: Path, path: Path) -> Path:
    root = Path(root).resolve(strict=True)
    path = Path(path)
    candidate = (
        path.resolve(strict=True) if path.is_absolute() else (root / path).resolve(strict=True)
    )
    if not root.is_dir() or not candidate.is_relative_to(root) or not candidate.is_file():
        raise MediaError("invalid_local_path")
    return candidate


def fingerprint(path: Path, cancel: Cancel = None) -> tuple[str, int]:
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            check_cancel(cancel)
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def snapshot(source: Path, destination: Path, cancel: Cancel) -> tuple[str, int]:
    before = source.stat()
    digest, size = hashlib.sha256(), 0
    with source.open("rb") as src, destination.open("xb") as dst:
        while chunk := src.read(1024 * 1024):
            check_cancel(cancel)
            digest.update(chunk)
            size += len(chunk)
            dst.write(chunk)
        dst.flush()
        os.fsync(dst.fileno())
    after = source.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or not size:
        raise MediaError("source_changed_or_empty")
    return digest.hexdigest(), size


def artifact(root: Path, path: Path, cancel: Cancel = None) -> Artifact:
    digest, size = fingerprint(path, cancel)
    return Artifact(path=path.relative_to(root).as_posix(), sha256=digest, size_bytes=size)


def verify_artifact(root: Path, item: Artifact) -> Path:
    if Path(item.path).is_absolute():
        raise MediaError("invalid_artifact_path")
    path = controlled_file(root, Path(item.path))
    if fingerprint(path) != (item.sha256, item.size_bytes):
        raise MediaError("artifact_integrity_failed")
    return path
