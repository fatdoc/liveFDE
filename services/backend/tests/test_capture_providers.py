import sys
from pathlib import Path

import pytest

from live_review.integrations.capture import providers
from live_review.integrations.capture.contracts import CaptureError, StopCapture
from live_review.integrations.capture.policy import CapturePolicy, load_policy
from live_review.integrations.capture.providers import CaptureRegistry, Source, canonical_reference


def test_registry_references_and_waiting_state():
    registry = CaptureRegistry(CapturePolicy())
    assert registry.get("wechat").probe("phone_cast", lambda: None) == Source(False)
    assert registry.get("wechat").health()["requires_phone"]
    for source in (
        "http://live.douyin.com/1",
        "https://v.douyin.com/a/",
        "https://live.douyin.com/1?token=x",
    ):
        with pytest.raises(CaptureError):
            canonical_reference("douyin", source)
    assert canonical_reference("douyin", "https://live.douyin.com/123/").endswith("/123")
    with pytest.raises(CaptureError, match="provider_dependencies_missing"):
        registry.get("douyin").acquire("https://live.douyin.com/123", lambda: None)


def test_finder_wait_receive_and_cancel(tmp_path, monkeypatch):
    executable = tmp_path / "finder"
    executable.write_text(
        "#!/usr/bin/env python3\nimport time\ntime.sleep(.2)\nprint('https://cdn.qq.com/live.m3u8?secret=abc')\n"
    )
    executable.chmod(0o700)
    provider = providers.FinderProvider(CapturePolicy(finder_executable=executable))
    ticks = []
    source = provider.acquire("phone_cast", lambda: ticks.append(True))
    assert ticks and source.live and "secret" not in repr(source)

    def stop():
        raise StopCapture

    with pytest.raises(StopCapture):
        provider.acquire("phone_cast", stop)


def test_douyin_offline_vs_parser_failure(tmp_path, monkeypatch):
    policy = CapturePolicy(
        root=tmp_path,
        douyin_python=Path(sys.executable),
        douyin_checkout=tmp_path,
        probe_attempts=1,
    )
    provider = providers.DouyinProvider(policy)
    monkeypatch.setattr(provider, "health", lambda: {"dependencies_ready": True})
    monkeypatch.setattr(
        providers.subprocess,
        "run",
        lambda *a, **k: type("R", (), {"stdout": providers.DOUYIN_COMMIT.encode()})(),
    )
    monkeypatch.setattr(providers, "communicate", lambda *a, **k: b'{"live":false}')
    assert not provider.probe("https://live.douyin.com/1", lambda: None).live
    monkeypatch.setattr(providers, "communicate", lambda *a, **k: b'{"error":"failed"}')
    with pytest.raises(CaptureError, match="source_parse_failed"):
        provider.probe("https://live.douyin.com/1", lambda: None)


def test_layered_policy_separate_from_model_registry(tmp_path):
    (tmp_path / "environments").mkdir()
    (tmp_path / "capture-policy.yaml").write_text("max_seconds: 60\n")
    (tmp_path / "environments/development.capture.yaml").write_text("max_seconds: 30\n")
    (tmp_path / "capture.local.yaml").write_text("max_seconds: 10\n")
    settings = type(
        "Settings",
        (),
        {
            "model_config_dir": tmp_path,
            "environment": "development",
            "model_config_environment": None,
        },
    )()
    assert load_policy(settings).max_seconds == 10
