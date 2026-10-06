"""Offline DNS fixtures/local child processes only; never resolves or probes a remote host."""

import json
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4

import pytest

from live_review.integrations.capture import recording, relay
from live_review.integrations.capture.contracts import CaptureError, Source, StopCapture
from live_review.integrations.capture.policy import CapturePolicy


def fixture_command(addresses):
    return [sys.executable, "-I", "-c", f"print({json.dumps(json.dumps(addresses))})"]


def supervise(monkeypatch, command=None):
    children = []
    original = subprocess.Popen

    def launch(args, **kwargs):
        assert args[0] == sys.executable, "no media executable or network tool is allowed"
        process = original(args, **kwargs)
        children.append(process)
        return process

    monkeypatch.setattr(relay.subprocess, "Popen", launch)
    monkeypatch.setattr(
        relay,
        "_resolver_command",
        lambda host, port: command or [sys.executable, "-I", "-c", "import time; time.sleep(60)"],
    )
    return children


def test_blocked_dns_deadline_terminates_and_reaps_child(monkeypatch):
    children = supervise(monkeypatch)
    began, calls = time.monotonic(), []
    with pytest.raises(CaptureError, match="duration_limit"):
        relay.resolve_addresses(
            "fixture.invalid", 443, deadline=began + 0.2, tick=lambda: calls.append(True)
        )
    assert time.monotonic() - began < 1.5 and len(calls) >= 2
    assert len(children) == 1 and children[0].poll() is not None
    assert children[0].stdout.closed


def test_stop_during_dns_wait_reaps_child(monkeypatch):
    children = supervise(monkeypatch)
    count = 0

    def tick():
        nonlocal count
        count += 1
        if count == 3:
            raise StopCapture

    with pytest.raises(StopCapture):
        relay.resolve_addresses("fixture.invalid", 443, tick=tick)
    assert children and all(child.poll() is not None for child in children)


def test_record_initial_dns_is_inside_total_budget(tmp_path, monkeypatch):
    children = supervise(monkeypatch)
    policy = CapturePolicy(
        max_seconds=1, min_free_bytes=1048576, stream_domains=["fixture.invalid"]
    )
    began = time.monotonic()
    with pytest.raises(CaptureError, match="duration_limit"):
        recording.record(
            Source(True, "https://fixture.invalid/live.m3u8"),
            tmp_path,
            policy,
            lambda: None,
            lambda _: None,
            "douyin",
            uuid4(),
            "fixture",
        )
    assert time.monotonic() - began < 2.5
    assert (tmp_path / "started.json").exists()
    assert not (tmp_path / "manifest.json").exists()
    assert children and all(child.poll() is not None for child in children)


def test_record_initial_dns_consumes_stop_without_media(tmp_path, monkeypatch):
    children = supervise(monkeypatch)
    calls = 0

    def stop():
        nonlocal calls
        calls += 1
        if calls >= 3:
            raise StopCapture

    with pytest.raises(StopCapture):
        recording.record(
            Source(True, "https://fixture.invalid/live.m3u8"),
            tmp_path,
            CapturePolicy(stream_domains=["fixture.invalid"], min_free_bytes=1048576),
            stop,
            lambda _: None,
            "douyin",
            uuid4(),
            "fixture",
        )
    assert children and all(child.poll() is not None for child in children)
    assert not (tmp_path / "manifest.json").exists()


def test_subresource_resolution_uses_same_deadline(monkeypatch):
    children = supervise(monkeypatch)
    monkeypatch.setattr(
        relay,
        "_resolver_command",
        lambda host, port: (
            fixture_command(["8.8.8.8"])
            if host == "first.invalid"
            else [sys.executable, "-I", "-c", "import time; time.sleep(60)"]
        ),
    )
    instance = relay.Relay(
        "https://first.invalid/main.m3u8", ["invalid"], deadline=time.monotonic() + 0.3
    )
    try:
        with pytest.raises(CaptureError, match="duration_limit"):
            instance.playlist(
                b"#EXTM3U\nhttps://child.invalid/part.ts\n", "https://first.invalid/main.m3u8"
            )
        assert len(children) == 2 and all(child.poll() is not None for child in children)
    finally:
        instance.server.server_close()


def permit_offline(url, domains):
    parts = urlsplit(url)
    return parts, "8.8.8.8", parts.port or (443 if parts.scheme == "https" else 80)


def test_https_only_applies_before_initial_dns_and_hls_registration(monkeypatch):
    calls = []

    def permitted(url, domains):
        calls.append(url)
        return permit_offline(url, domains)

    monkeypatch.setattr(relay, "destination", permitted)
    with pytest.raises(CaptureError, match="https_required"):
        relay.Relay("http://fixture.invalid/main.m3u8", ["fixture.invalid"], https_only=True)
    assert not calls
    instance = relay.Relay(
        "https://fixture.invalid/main.m3u8", ["fixture.invalid"], https_only=True
    )
    try:
        with pytest.raises(CaptureError, match="https_required"):
            instance.playlist(
                b"#EXTM3U\nhttp://fixture.invalid/a.ts\n", "https://fixture.invalid/main.m3u8"
            )
        assert len(calls) == 1
    finally:
        instance.server.server_close()


def test_https_only_rejects_redirect_before_second_connection(monkeypatch):
    monkeypatch.setattr(relay, "destination", permit_offline)
    connections = []

    class Connection:
        def __init__(self, *args, **kwargs):
            connections.append(self)

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return SimpleNamespace(status=302, getheader=lambda _: "http://fixture.invalid/a.ts")

        def close(self):
            pass

    monkeypatch.setattr(relay.http.client, "HTTPConnection", Connection)
    monkeypatch.setattr(relay.socket, "create_connection", lambda *a, **k: object())
    monkeypatch.setattr(
        relay.ssl,
        "create_default_context",
        lambda: SimpleNamespace(wrap_socket=lambda *a, **k: object()),
    )
    instance = relay.Relay(
        "https://fixture.invalid/main.m3u8", ["fixture.invalid"], https_only=True
    )
    try:
        with pytest.raises(CaptureError, match="https_required"):
            instance.fetch("https://fixture.invalid/main.m3u8", None)
        assert len(connections) == 1
    finally:
        instance.server.server_close()


def test_http_and_both_platforms_remain_defaults(monkeypatch):
    policy = CapturePolicy()
    assert policy.allowed_platforms == ["douyin", "wechat"] and not policy.https_only
    monkeypatch.setattr(relay, "destination", permit_offline)
    instance = relay.Relay("http://fixture.invalid/main.m3u8", ["fixture.invalid"])
    instance.server.server_close()


def test_all_dns_answers_must_be_public(monkeypatch):
    monkeypatch.setattr(relay, "resolve_addresses", lambda *a, **k: ["8.8.8.8", "127.0.0.1"])
    with pytest.raises(CaptureError, match="unsafe_stream_url"):
        relay.destination("https://fixture.invalid/a", ["fixture.invalid"])


def test_relay_close_stops_active_child_resolution(monkeypatch):
    children = supervise(monkeypatch, fixture_command(["8.8.8.8"]))
    instance = relay.Relay("https://fixture.invalid/a", ["fixture.invalid"])
    monkeypatch.setattr(
        relay,
        "_resolver_command",
        lambda *a: [sys.executable, "-I", "-c", "import time; time.sleep(60)"],
    )
    errors = []

    def resolve_child():
        try:
            instance.register("https://fixture.invalid/child")
        except StopCapture:
            errors.append("stopped")

    with instance:
        thread = threading.Thread(target=resolve_child)
        thread.start()
        deadline = time.monotonic() + 2
        while len(children) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
    thread.join(timeout=1)
    assert not thread.is_alive() and errors == ["stopped"]
    assert len(children) == 2 and all(child.poll() is not None for child in children)


def test_stubborn_resolver_is_killed_and_reaped(tmp_path, monkeypatch):
    ready = tmp_path / "ready"
    command = [
        sys.executable,
        "-I",
        "-c",
        (
            "import signal,time,pathlib; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
            f"pathlib.Path({str(ready)!r}).write_text('ready'); time.sleep(60)"
        ),
    ]
    children = supervise(monkeypatch, command)
    with pytest.raises(CaptureError, match="duration_limit"):
        relay.resolve_addresses("fixture.invalid", 443, deadline=time.monotonic() + 0.5)
    assert ready.exists() and len(children) == 1
    assert children[0].returncode == -9 and children[0].stdout.closed


def test_loopback_server_never_reverse_resolves_its_bind_address(monkeypatch):
    monkeypatch.setattr(relay, "destination", permit_offline)

    def forbidden(*args):
        raise AssertionError("loopback bind must not start an uncontrolled resolver")

    monkeypatch.setattr(relay.socket, "getfqdn", forbidden)
    instance = relay.Relay("http://fixture.invalid/main.m3u8", ["fixture.invalid"])
    instance.server.server_close()
