"""Workspace-scoped OS-permission protected credentials outside downloadable storage."""

import fcntl
import json
import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

from live_review.core.errors import ApiError
from live_review.integrations.capture.providers import DOUYIN_ERRORS


@dataclass(frozen=True)
class Snapshot:
    revision: str = "0"
    cookie: str = field(default="", repr=False)
    status: str = "not_configured"
    checked_at: str | None = None
    checked_source: str | None = None
    checked_state: str | None = None
    last_error: str | None = None

    def public(self, service_ready):
        return {
            "revision": self.revision,
            "configured": bool(self.cookie),
            "status": self.status,
            "checked_at": self.checked_at,
            "checked_source": self.checked_source,
            "checked_state": self.checked_state,
            "last_error": self.last_error,
            "service_ready": service_ready,
        }


class CredentialStore:
    def __init__(self, settings, workspace_id):
        if settings.storage_root is None:
            raise ApiError(503, "platform_storage_unavailable", "平台设置暂不可用")
        root = Path(settings.storage_root)
        if not root.is_absolute() or root.resolve() != root:
            raise ApiError(503, "platform_storage_unavailable", "平台设置暂不可用")
        self.path = root.parent / "private" / "capture" / str(UUID(str(workspace_id)))
        try:
            for directory in (self.path.parent.parent, self.path.parent, self.path):
                directory.mkdir(mode=0o700, exist_ok=True)
                info = directory.lstat()
                if (
                    not stat.S_ISDIR(info.st_mode)
                    or directory.resolve() != directory
                    or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o700
                ):
                    raise OSError
        except OSError:
            raise ApiError(503, "platform_storage_unavailable", "平台设置暂不可用") from None

    @contextmanager
    def lock(self, name="settings.lock"):
        fd = None
        try:
            fd = os.open(
                self.path / name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600
            )
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
            ):
                raise OSError
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ApiError(
                    409, "platform_settings_busy", "已有平台操作正在进行，请稍后重试"
                ) from None
            yield
        except OSError:
            raise ApiError(503, "platform_storage_unavailable", "平台设置暂不可用") from None
        finally:
            if fd is not None:
                os.close(fd)

    def _read(self):
        try:
            fd = os.open(self.path / "douyin.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return Snapshot()
        except OSError:
            raise ApiError(503, "platform_storage_unavailable", "平台设置暂不可用") from None
        try:
            with os.fdopen(fd) as source:
                info = os.fstat(source.fileno())
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_size > 32768
                ):
                    raise ValueError
                data = json.loads(source.read(32769))
            result = Snapshot(**data)
            if (
                not isinstance(result.cookie, str)
                or len(result.cookie) > 16384
                or not isinstance(result.revision, str)
                or len(result.revision) > 64
                or result.status
                not in {"not_configured", "unverified", "verified", "needs_update", "check_failed"}
                or result.last_error not in DOUYIN_ERRORS | {None}
                or result.checked_state not in {"live", "not_live", None}
            ):
                raise ValueError
            return result
        except (OSError, ValueError, TypeError):
            raise ApiError(503, "platform_storage_unavailable", "平台设置暂不可用") from None

    def read(self):
        with self.lock():
            return self._read()

    def _write(self, snapshot):
        temporary = self.path / (uuid4().hex + ".tmp")
        try:
            fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w") as target:
                json.dump(vars(snapshot), target, ensure_ascii=True)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self.path / "douyin.json")
            fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            raise ApiError(503, "platform_storage_unavailable", "平台设置暂不可用") from None
        finally:
            temporary.unlink(missing_ok=True)

    def update(self, expected_revision, cookie):
        with self.lock():
            self.require_revision(self._read(), expected_revision)
            result = Snapshot(
                revision=uuid4().hex,
                cookie=cookie,
                status="unverified" if cookie else "not_configured",
            )
            self._write(result)
            return result

    def finish_check(self, previous, *, checked_at, source, state, error):
        with self.lock():
            self.require_revision(self._read(), previous.revision)
            status = (
                "verified"
                if error is None
                else ("needs_update" if error == "source_auth_required" else "check_failed")
            )
            result = Snapshot(
                revision=previous.revision,
                cookie=previous.cookie,
                status=status,
                checked_at=checked_at,
                checked_source=source,
                checked_state=state,
                last_error=error,
            )
            self._write(result)
            return result

    @staticmethod
    def require_revision(snapshot, expected):
        if snapshot.revision != expected:
            raise ApiError(409, "revision_conflict", "平台设置已更新，请刷新后重试")
