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
        f"#!{sys.executable}\nimport time,os,signal\n"
        + ("os.kill(os.getpid(), signal.SIGKILL)\n" if mode == "crash" else "time.sleep(20)\n")
    )
    script.chmod(0o700)
    original_popen = subprocess.Popen

    def ready_process(command, **kwargs):
        if command[0] == str(script):
            # Synchronize the synthetic file before returning the fake launch. This
            # tests stop/finalize semantics, not whether Python cold-starts in 1s.
            import shutil

            shutil.copyfile(av_file, command[-1])
            if mode == "size":
                with open(command[-1], "ab") as stream:
                    stream.truncate(1200000)
        process = original_popen(command, **kwargs)
        if command[0] == str(script) and mode == "crash":
            # Observe the injected crash before the recorder stall clock starts.
            process.wait(timeout=15)
        return process

    monkeypatch.setattr(recording.subprocess, "Popen", ready_process)
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


@pytest.mark.parametrize(
    "tag,attributes",
    [
        ("EXT-X-KEY", "METHOD=AES-128,"),
        ("EXT-X-SESSION-KEY", "METHOD=AES-128,"),
        ("EXT-X-MAP", ""),
        ("EXT-X-MEDIA", 'TYPE=AUDIO,GROUP-ID="a",NAME="a",'),
        ("EXT-X-I-FRAME-STREAM-INF", "BANDWIDTH=1000,"),
        ("EXT-X-SESSION-DATA", 'DATA-ID="test",'),
        ("EXT-X-PART", "DURATION=1,"),
        ("EXT-X-PRELOAD-HINT", "TYPE=PART,"),
        ("EXT-X-RENDITION-REPORT", ""),
    ],
)
def test_hls_uri_attributes_strictly_parsed_without_network(tag, attributes):
    from live_review.integrations.capture.hls import rewrite

    calls = []

    def registered(url, kind):
        calls.append((url, kind))
        return "http://127.0.0.1/opaque." + ("m3u8" if kind == "playlist" else "ts")

    body = f'#EXTM3U\n#{tag}:{attributes}URI="https://cdn.example.test/asset?opaque=1"\n'
    rendered = rewrite(body.encode(), "https://cdn.example.test/index.m3u8", registered)
    assert len(calls) == 1 and b"opaque=1" not in rendered
    calls.clear()
    for value in ("https://cdn.example.test/asset", '"valid",URI="duplicate"', '"unterminated'):
        with pytest.raises(CaptureError):
            rewrite(
                f"#EXTM3U\n#{tag}:{attributes}URI={value}\n".encode(),
                "https://cdn.example.test/index.m3u8",
                registered,
            )
        assert not calls  # Reject before registering any malformed URI, no requests involved.


def test_hls_unknown_extensions_and_attribute_syntax_fail_closed():
    from live_review.integrations.capture.hls import rewrite

    for line in (
        '#EXT-X-DEFINE:NAME="x",VALUE="value"',
        '#EXT-X-MAP:URI="file",UNKNOWN="x"',
        '#EXT-X-MAP:URI="file",',
        '#EXT-X-MAP:URI="file"garbage',
        '#EXT-X-FUTURE:URI="file"',
    ):
        with pytest.raises(CaptureError):
            rewrite(
                ("#EXTM3U\n" + line + "\n").encode(),
                "https://cdn.example.test/a",
                lambda url, kind: "http://127.0.0.1/opaque.ts",
            )


@pytest.mark.parametrize("encrypted", [False, True])
def test_actual_hls_ts_relay_records_audio_video(tmp_path, av_file, monkeypatch, encrypted):
    playlist = tmp_path / "index.m3u8"
    key_args = []
    if encrypted:
        key = tmp_path / "synthetic.key"
        key.write_bytes(b"0123456789abcdef")
        key_info = tmp_path / "key-info.txt"
        key_info.write_text("synthetic.key\n" + str(key) + "\n")
        key_args = ["-hls_key_info_file", str(key_info)]
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(av_file),
            "-c",
            "copy",
            "-f",
            "hls",
            "-hls_time",
            "1",
            "-hls_list_size",
            "0",
            *key_args,
            str(playlist),
        ],
        capture_output=True,
        check=True,
        timeout=15,
    )
    monkeypatch.setattr(relay, "destination", permit_fixture)
    target = tmp_path / "recorded-hls"
    target.mkdir()
    with http_source(playlist) as source:
        manifest = recording.record(
            Source(True, source),
            target,
            CapturePolicy(min_free_bytes=1048576, max_seconds=15),
            lambda: None,
            lambda _: None,
            "wechat",
            uuid4(),
            "phone_cast",
        )
    assert {"audio", "video"} <= set(manifest["media_types"])
    assert 1500 <= manifest["duration_ms"] <= 3000
    assert manifest["end_reason"] == "source_eof_unconfirmed" and not manifest["complete"]
    decoded = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(target / "recording.mp4"), "-f", "null", "-"],
        capture_output=True,
        check=False,
        timeout=15,
    )
    assert decoded.returncode == 0
