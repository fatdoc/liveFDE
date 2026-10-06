"""One recording, explicit process exit + media validation + atomic close manifest."""

import hashlib
import json
import os
import queue
import shutil
import signal
import subprocess
import threading
import time
from datetime import UTC, datetime

from live_review.integrations.capture.contracts import CaptureError, StopCapture
from live_review.integrations.capture.relay import Relay


def utcnow():
    return datetime.now(UTC).isoformat()


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    with temporary.open("x") as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def inspect_media(path, ffprobe):
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True,
        timeout=30,
    )
    try:
        data = json.loads(result.stdout)
        types = {s["codec_type"] for s in data["streams"]}
        duration = float(data["format"]["duration"])
        if result.returncode or not {"audio", "video"} <= types or not 0 < duration < 172800:
            raise ValueError
        return round(duration * 1000), sorted(types)
    except (ValueError, KeyError):
        raise CaptureError("invalid_recorded_media") from None


def close_process(process):
    if process.poll() is None:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
            raise CaptureError("recording_stop_unconfirmed") from None


def record(source, directory, policy, tick, progress, platform, run_id, reference):
    # Acquisition's DNS/setup time belongs to this recording budget, not a later FFmpeg clock.
    deadline = time.monotonic() + policy.max_seconds
    if shutil.disk_usage(directory).free < policy.min_free_bytes:
        raise CaptureError("disk_full")
    target = directory / "recording.partial.mp4"
    started = utcnow()
    # Marker prevents silently starting a new live interval after worker loss.
    atomic_json(directory / "started.json", {"started_at": started})
    events = queue.Queue()
    reason, recorded = "source_eof_unconfirmed", False
    with Relay(
        source.url,
        policy.stream_domains,
        deadline=deadline,
        tick=tick,
        https_only=policy.https_only,
    ) as relay:
        tick()
        if time.monotonic() >= deadline:
            raise CaptureError("duration_limit")
        command = [
            policy.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-rw_timeout",
            "10000000",
            "-protocol_whitelist",
            "http,tcp,crypto",
            "-format_whitelist",
            "hls,flv,mpegts,mov",
            "-i",
            relay.url,
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+frag_keyframe+empty_moov+default_base_moof",
            "-progress",
            "pipe:1",
            "-t",
            str(policy.max_seconds),
            "-fs",
            str(policy.max_bytes),
            "-n",
            str(target),
        ]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

        def drain():
            for line in process.stdout:
                if line.startswith(b"out_time_us="):
                    try:
                        events.put(int(line.split(b"=", 1)[1]))
                    except ValueError:
                        pass

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        last_progress = time.monotonic()
        out_time = 0
        try:
            while process.poll() is None:
                tick()
                while not events.empty():
                    value = events.get_nowait()
                    if value > out_time:
                        out_time, last_progress = value, time.monotonic()
                        if not recorded:
                            recorded = True
                            progress("recording")
                if shutil.disk_usage(directory).free < policy.min_free_bytes:
                    reason = "disk_full"
                    break
                if time.monotonic() >= deadline:
                    reason = "duration_limit"
                    break
                if target.exists() and target.stat().st_size >= policy.max_bytes:
                    reason = "size_limit"
                    break
                if time.monotonic() - last_progress > policy.stall_seconds:
                    reason = relay.error or "stream_stalled"
                    break
                time.sleep(0.1)
        except StopCapture:
            reason = "user_stop"
        finally:
            close_process(process)
            reader.join(timeout=2)
            process.stdout.close()
        ended = utcnow()
        if relay.error and reason == "source_eof_unconfirmed":
            reason = relay.error
        elif process.returncode and reason == "source_eof_unconfirmed":
            reason = "process_crashed" if process.returncode < 0 else "stream_disconnected"
        elif out_time >= policy.max_seconds * 1000000 - 1000000:
            reason = "duration_limit" if reason == "source_eof_unconfirmed" else reason
        elif target.exists() and target.stat().st_size >= policy.max_bytes:
            reason = "size_limit" if reason == "source_eof_unconfirmed" else reason
    if not target.exists() or target.stat().st_size == 0:
        raise CaptureError(reason if reason != "user_stop" else "stopped_without_media")
    try:
        duration, types = inspect_media(target, policy.ffprobe)
    except CaptureError:
        raise CaptureError(
            reason if reason != "source_eof_unconfirmed" else "invalid_recorded_media"
        ) from None
    with target.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    with target.open("rb") as stream:
        os.fsync(stream.fileno())
    final = directory / "recording.mp4"
    os.replace(target, final)
    manifest = {
        "schema_version": 1,
        "platform": platform,
        "capture_run_id": str(run_id),
        "source_ref": reference,
        "started_at": started,
        "ended_at": ended,
        "duration_ms": duration,
        "sha256": digest,
        "size_bytes": final.stat().st_size,
        "media_types": types,
        "file": "recording.mp4",
        "segment_index": 0,
        "complete": reason == "user_stop",
        "end_reason": reason,
        "closed": True,
    }
    atomic_json(directory / "manifest.json", manifest)
    return manifest
