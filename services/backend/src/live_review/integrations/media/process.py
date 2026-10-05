"""Bounded FFmpeg process calls; inherit the job handler's process group."""

import subprocess
import tempfile
import time
from collections.abc import Callable

Cancel = Callable[[], bool] | None


class MediaError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def check_cancel(cancel: Cancel):
    if cancel and cancel():
        raise MediaError("canceled")


def run_process(args: list[str], *, timeout: float, cancel: Cancel = None) -> bytes:
    if timeout <= 0:
        raise MediaError("invalid_timeout")
    check_cancel(cancel)
    started = time.monotonic()
    # Files avoid pipe deadlocks and unbounded communicate() buffers. They are
    # private transient OS files, not persisted logs containing customer paths.
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
        except FileNotFoundError as error:
            raise MediaError("tool_unavailable") from error
        try:
            while process.poll() is None:
                check_cancel(cancel)
                if time.monotonic() - started > timeout:
                    raise MediaError("process_timeout")
                if out.tell() > 2 * 1024 * 1024 or err.tell() > 2 * 1024 * 1024:
                    raise MediaError("process_output_limit")
                time.sleep(0.025)
            check_cancel(cancel)
            if process.returncode:
                raise MediaError("media_decode_failed")
            out.seek(0)
            output = out.read(2 * 1024 * 1024 + 1)
            if len(output) > 2 * 1024 * 1024:
                raise MediaError("process_output_limit")
            return output
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
