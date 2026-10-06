"""OS-private files with atomic replacement; no YAML or downloadable object storage."""

import fcntl
import os
import stat
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

from live_review.core.errors import ApiError


def unavailable():
    return ApiError(503, "llm_storage_unavailable", "大模型设置暂不可用")


class PrivateFiles:
    def __init__(self, settings, workspace_id):
        try:
            root = Path(settings.storage_root)
            if not root.is_absolute() or root.resolve() != root:
                raise ValueError
            self.path = root.parent / "private" / "llm" / str(UUID(str(workspace_id)))
            for directory in (self.path.parent.parent, self.path.parent, self.path):
                directory.mkdir(mode=0o700, exist_ok=True)
                info = directory.lstat()
                if (
                    not stat.S_ISDIR(info.st_mode)
                    or directory.resolve() != directory
                    or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o700
                ):
                    raise ValueError
        except (OSError, TypeError, ValueError):
            raise unavailable() from None

    @contextmanager
    def lock(self, name="settings.lock"):
        fd = None
        try:
            fd = os.open(
                self.path / name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600
            )
            self.validate(fd, 0)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ApiError(409, "llm_settings_busy", "已有操作正在进行，请稍后查看") from None
            yield
        except OSError:
            raise unavailable() from None
        finally:
            if fd is not None:
                os.close(fd)

    @staticmethod
    def validate(fd, maximum):
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_size > maximum
        ):
            raise unavailable()

    def read(self, name, maximum):
        try:
            fd = os.open(self.path / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as source:
                self.validate(source.fileno(), maximum)
                value = source.read(maximum + 1)
                if len(value) > maximum:
                    raise unavailable()
                return value
        except FileNotFoundError:
            return None
        except OSError:
            raise unavailable() from None

    def write(self, name, content):
        temporary = self.path / (uuid4().hex + ".tmp")
        try:
            fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as target:
                target.write(content)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self.path / name)
            fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            raise unavailable() from None
        finally:
            temporary.unlink(missing_ok=True)
