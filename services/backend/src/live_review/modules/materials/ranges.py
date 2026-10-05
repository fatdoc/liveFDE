import re

from live_review.core.errors import ApiError


class UnsatisfiableRange(Exception):
    pass


def select_range(header: str | None, size: int, if_range: str | None, etag: str):
    if header is None or (if_range is not None and if_range != etag):
        return None
    if len(header) > 2048 or not header.startswith("bytes="):
        raise ApiError(400, "invalid_range", "Range 格式不正确")
    parts = header[6:].split(",")
    for part in parts:
        if not re.fullmatch(r"[0-9]*-[0-9]*", part.strip()) or part.strip() == "-":
            raise ApiError(400, "invalid_range", "Range 格式不正确")
    if len(parts) > 1:
        return None
    start, end = parts[0].strip().split("-")
    if not start:
        count = int(end)
        if count == 0 or size == 0:
            raise UnsatisfiableRange
        return max(0, size - count), size - 1
    start = int(start)
    explicit_end = bool(end)
    end = int(end) if end else size - 1
    if explicit_end and end < start:
        raise ApiError(400, "invalid_range", "Range 结束位置小于开始位置")
    if start >= size:
        raise UnsatisfiableRange
    return start, min(end, size - 1)
