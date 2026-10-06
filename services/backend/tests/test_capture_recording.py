import contextlib
import functools
import json
import socket
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from capture_fixture import av_file as av_file

from live_review.integrations.capture import recording, relay
from live_review.integrations.capture.contracts import CaptureError, Source, StopCapture
from live_review.integrations.capture.policy import CapturePolicy


@contextlib.contextmanager
def http_source(path):
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Handler, directory=str(path.parent))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/{path.name}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def permit_fixture(url, domains):
    parts = urlsplit(url)
    assert parts.hostname == "127.0.0.1"
    return parts, "127.0.0.1", parts.port


def test_actual_av_active_stop_and_atomic_manifest(tmp_path, av_file, monkeypatch):
    monkeypatch.setattr(relay, "destination", permit_fixture)
    original = subprocess.Popen
    commands = []

    def paced(command, **kwargs):
        commands.append(command)
        if command[0] == "ffmpeg" and "-progress" in command:
            index = command.index("-i")
            command = command[:index] + ["-re"] + command[index:]
        return original(command, **kwargs)

    monkeypatch.setattr(recording.subprocess, "Popen", paced)
    path = tmp_path / "capture"
    path.mkdir()
    policy = CapturePolicy(min_free_bytes=1048576, max_seconds=15)
    states = []

    def tick():
        if states:
            raise StopCapture

    with http_source(av_file) as url:
        manifest = recording.record(
            Source(True, url), path, policy, tick, states.append, "wechat", uuid4(), "phone_cast"
        )
    assert states == ["recording"]
    assert manifest["closed"] and manifest["end_reason"] == "user_stop"
    assert {"audio", "video"} <= set(manifest["media_types"])
    assert 100 <= manifest["duration_ms"] <= 3000
    assert (path / "manifest.json").exists() and not (path / "recording.partial.mp4").exists()
    assert manifest == json.loads((path / "manifest.json").read_text())
    assert all("phone_cast" not in arg for arg in commands[0])
    # Decode whole recording, not merely checking extensions or file size.
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path / "recording.mp4"), "-f", "null", "-"],
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0


def test_disk_preflight(tmp_path, monkeypatch):
    monkeypatch.setattr(recording.shutil, "disk_usage", lambda _: type("D", (), {"free": 1})())
    with pytest.raises(CaptureError, match="disk_full"):
        recording.record(
            Source(True, "unused"),
            tmp_path,
            CapturePolicy(),
            lambda: None,
            lambda _: None,
            "douyin",
            uuid4(),
            "room",
        )
    assert not (tmp_path / "started.json").exists()


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("crash", "process_crashed"),
        ("disk", "disk_full"),
        ("stall", "stream_stalled"),
        ("duration", "duration_limit"),
        ("size", "size_limit"),
    ],
)
def test_interruption_preserves_closed_partial(tmp_path, av_file, monkeypatch, mode, expected):
    # Controlled process fault with a real AV file; separate from actual FFmpeg test above.
    script = tmp_path / "fault-process"
    script.write_text(
        f"#!{sys.executable}\nimport sys,shutil,time,os,signal\n"
        + f"shutil.copyfile({str(av_file)!r}, sys.argv[-1])\n"
        + ("with open(sys.argv[-1], 'ab') as f: f.truncate(1200000)\n" if mode == "size" else "")
        + ("os.kill(os.getpid(), signal.SIGKILL)\n" if mode == "crash" else "time.sleep(20)\n")
    )
    script.chmod(0o700)
    monkeypatch.setattr(relay, "destination", permit_fixture)
    count = [0]
    real_disk = recording.shutil.disk_usage

    def disk(path):
        count[0] += 1
        if mode == "disk" and (tmp_path / "recording.partial.mp4").exists():
            return type("D", (), {"free": 1})()
        return real_disk(path)

    monkeypatch.setattr(recording.shutil, "disk_usage", disk)
    policy = CapturePolicy(
        ffmpeg=str(script),
        max_bytes=1048576,
        min_free_bytes=1048576,
        max_seconds=1 if mode == "duration" else 10,
        stall_seconds=2,
    )
    with http_source(av_file) as url:
        manifest = recording.record(
            Source(True, url),
            tmp_path,
            policy,
            lambda: None,
            lambda _: None,
            "wechat",
            uuid4(),
            "phone_cast",
        )
    assert manifest["end_reason"] == expected
    assert manifest["closed"] and not manifest["complete"]
    assert (tmp_path / "recording.mp4").exists()


def test_ssrf_hls_and_redirect_validation(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(CaptureError, match="unsafe_stream_url"):
        relay.destination("https://cdn.qq.com/a", ["qq.com"])
    for url in ("file:///etc/passwd", "https://qq.com.evil.test/a", "http://169.254.169.254/a"):
        with pytest.raises(CaptureError):
            relay.destination(url, ["qq.com"])
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("8.8.8.8", 443))])
    instance = relay.Relay("https://cdn.qq.com/live.m3u8?secret=one", ["qq.com"])
    try:
        rewritten = instance.playlist(
            b'#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="key?secret=two"\nseg.ts?secret=three\n',
            "https://cdn.qq.com/live.m3u8",
        )
        assert b"secret" not in rewritten and b"127.0.0.1" in rewritten
        with pytest.raises(CaptureError):
            instance.playlist(b"#EXTM3U\nfile:///etc/passwd\n", "https://cdn.qq.com/live.m3u8")
    finally:
        instance.server.server_close()


def test_address_expired_no_closed_media(tmp_path, monkeypatch):
    from http.server import BaseHTTPRequestHandler

    class Expired(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(403)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Expired)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(relay, "destination", permit_fixture)
    try:
        with pytest.raises(CaptureError, match="address_expired"):
            recording.record(
                Source(True, f"http://127.0.0.1:{server.server_port}/expired"),
                tmp_path,
                CapturePolicy(min_free_bytes=1048576),
                lambda: None,
                lambda _: None,
                "wechat",
                uuid4(),
                "phone_cast",
            )
        assert not (tmp_path / "manifest.json").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
