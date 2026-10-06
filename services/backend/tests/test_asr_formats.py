"""Actual FFmpeg containers, not a suffix-only allowlist."""

import subprocess

import pytest

from live_review.core.errors import ApiError
from live_review.modules.materials.schemas import UploadInput
from live_review.modules.materials.validation import validate_file


@pytest.mark.parametrize("suffix,media_type", [("m4a", "audio/mp4"), ("aac", "audio/aac")])
def test_real_new_audio_containers(tmp_path, suffix, media_type):
    path = tmp_path / f"synthetic.{suffix}"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.2",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
    )
    size = path.stat().st_size
    UploadInput(filename=path.name, byte_size=size, media_type=media_type, purpose="session_media")
    assert len(validate_file(path, size, None, media_type, "session_media", "ffprobe")) == 64
    with pytest.raises(ApiError):
        validate_file(path, size, None, "audio/mpeg", "session_media", "ffprobe")
    path.write_bytes(b"not media")
    with pytest.raises(ApiError):
        validate_file(path, path.stat().st_size, None, media_type, "session_media", "ffprobe")
