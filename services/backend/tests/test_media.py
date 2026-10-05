import hashlib
import json
import shutil
import subprocess
import sys
import time
import wave

import pytest

from live_review.integrations.media import MediaError, extract_audio
from live_review.integrations.media.process import run_process


@pytest.fixture
def media_source(tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("Real ffmpeg/ffprobe required")
    source = tmp_path / "input"
    source.mkdir()
    audio = source / "source.wav"
    with wave.open(str(audio), "wb") as output:
        output.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
        output.writeframes(b"\x00\x01\x00\x02" * 144003)
    return source, audio, tmp_path / "artifacts"


def test_real_extract_sample_partition_and_provenance(media_source):
    root, source, output = media_source
    result = extract_audio(source, input_root=root, output_root=output, segment_seconds=1)
    assert result.source_sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert result.sample_rate == 16000 and result.channels == 1
    assert result.audio_samples > 48000
    assert result.segments[0].start_sample == 0
    assert result.segments[-1].end_sample == result.audio_samples
    assert all(
        a.end_sample == b.start_sample
        for a, b in zip(result.segments, result.segments[1:], strict=False)
    )
    joined = b""
    for segment in result.segments:
        with wave.open(str(output / segment.artifact.path), "rb") as wav:
            assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (16000, 1, 2)
            joined += wav.readframes(wav.getnframes())
    with wave.open(str(output / result.audio.path), "rb") as wav:
        assert joined == wav.readframes(wav.getnframes())
    assert not list(output.rglob("*.snapshot"))
    assert json.loads(result.model_dump_json())["source_integrity"] == "verified_snapshot"


def test_real_video_extract_and_missing_audio(media_source):
    root, _, output = media_source
    video = root / "video.mkv"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=32x32:r=5:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-c:v",
            "ffv1",
            "-c:a",
            "pcm_s16le",
            "-y",
            str(video),
        ],
        check=True,
    )
    result = extract_audio(video, input_root=root, output_root=output)
    assert result.audio_samples == 16000
    silent = root / "silent.mkv"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video), "-an", "-c:v", "copy", str(silent)], check=True
    )
    with pytest.raises(MediaError, match="no_audio_track"):
        extract_audio(silent, input_root=root, output_root=output)


def test_corruption_paths_playlist_and_limits(media_source, tmp_path):
    root, source, output = media_source
    bad = root / "bad.mp4"
    bad.write_bytes(b"not media")
    with pytest.raises(MediaError, match="media_decode_failed"):
        extract_audio(bad, input_root=root, output_root=output)
    playlist = root / "remote.m3u8"
    playlist.write_text("#EXTM3U\n#EXTINF:1,\nhttp://127.0.0.1:9/private.ts\n")
    with pytest.raises(MediaError, match="media_decode_failed"):
        extract_audio(playlist, input_root=root, output_root=output)
    outside = tmp_path / "outside.wav"
    outside.write_bytes(source.read_bytes())
    link = root / "escape.wav"
    link.symlink_to(outside)
    with pytest.raises(MediaError, match="invalid_local_path"):
        extract_audio(link, input_root=root, output_root=output)
    with pytest.raises(MediaError, match="source_duration_limit"):
        extract_audio(source, input_root=root, output_root=output, max_duration_seconds=1)
    assert list(output.iterdir()) == []


def test_timeout_and_cancel_join_process(monkeypatch):
    original = subprocess.Popen
    processes = []

    def record(*args, **kwargs):
        assert isinstance(args[0], list) and not kwargs.get("shell")
        assert not kwargs.get("start_new_session")
        child = original(*args, **kwargs)
        processes.append(child)
        return child

    monkeypatch.setattr(subprocess, "Popen", record)
    command = [sys.executable, "-c", "import time; time.sleep(30)"]
    with pytest.raises(MediaError, match="process_timeout"):
        run_process(command, timeout=0.1)
    start = time.monotonic()
    with pytest.raises(MediaError, match="canceled"):
        run_process(command, timeout=10, cancel=lambda: time.monotonic() - start > 0.1)
    assert all(child.poll() is not None for child in processes)


def test_cancel_source_copy_cleans_owned_output(media_source):
    root, source, output = media_source
    with pytest.raises(MediaError, match="canceled"):
        extract_audio(source, input_root=root, output_root=output, cancel=lambda: True)
    assert list(output.iterdir()) == []


def test_delayed_audio_preserves_source_offset(media_source):
    root, _, output = media_source
    video = root / "delayed.mkv"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=32x32:r=10:d=2",
            "-itsoffset",
            "0.5",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-c:v",
            "ffv1",
            "-c:a",
            "pcm_s16le",
            str(video),
        ],
        check=True,
    )
    result = extract_audio(video, input_root=root, output_root=output, segment_seconds=1)
    assert result.audio_offset_ms == 500
    assert result.segments[0].start_ms == 500
    assert result.segments[-1].end_ms == 1500
