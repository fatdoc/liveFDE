"""Only UUID keys; filenames and user URLs never become filesystem paths."""

import os
import shutil
from pathlib import Path
from uuid import UUID

from live_review.core.errors import ApiError


class LocalStorage:
    def __init__(self, root: Path | None):
        if root is None or not Path(root).is_absolute():
            raise ApiError(503, "storage_not_configured", "文件存储尚未配置")
        self.root = Path(root).resolve()

    def path(self, kind: str, key: UUID, suffix: str = "") -> Path:
        if kind not in {"uploads", "blobs"} or suffix not in {"", ".part"}:
            raise ValueError("Invalid internal storage namespace")
        key = UUID(str(key))
        path = self.root / kind / f"{key}{suffix}"
        if not path.resolve().is_relative_to(self.root):
            raise ApiError(503, "storage_path_invalid", "存储路径不可用")
        return path

    def prepare(self, kind: str, key: UUID, suffix: str = "") -> Path:
        path = self.path(kind, key, suffix)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def promote_copy(self, source: Path, key: UUID) -> Path:
        target = self.prepare("blobs", key)
        temporary = self.prepare("blobs", key, ".part")
        # Source remains intact until the DB commit, making finalization replayable.
        with source.open("rb") as src, temporary.open("wb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        os.replace(temporary, target)
        return target
