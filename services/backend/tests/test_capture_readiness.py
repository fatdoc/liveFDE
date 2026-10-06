"""Readiness uses local configuration only; no real platform or resolver requests."""

import json

import pytest
from capture_fixture import capture_env as capture_env
from capture_fixture import materials as materials
from capture_fixture import start_run
from test_capture_executor import native, ready

from live_review.integrations.capture.policy import CapturePolicy, load_policy
from live_review.modules.capture.readiness import platform_conditions

ONLINE = {"ready": True, "automatic_dispatch": True}


@pytest.mark.parametrize("domains", [[], ["*"], ["https://douyincdn.com"], ["127.0.0.1"]])
def test_domains_fail_closed_without_external_probe(monkeypatch, domains):
    monkeypatch.setattr(
        "live_review.integrations.capture.providers.DouyinProvider.health",
        lambda _: {"dependencies_ready": True, "real_platform_verified": False},
    )
    policy = CapturePolicy(enabled=True, stream_domains=domains)
    result = platform_conditions(policy, "douyin", ONLINE, True, True)
    assert not result["start_ready"] and not result["source_access_configured"]
    assert result["blockers"][0]["code"] == "capture_source_access_not_configured"
    assert not result["real_platform_verified"]


def test_online_executor_does_not_imply_provider_ready():
    result = platform_conditions(CapturePolicy(enabled=True), "douyin", ONLINE, True, True)
    assert not result["start_ready"]
    assert result["blockers"][0]["code"] == "provider_dependencies_missing"
    assert "cookie" not in json.dumps(result["blockers"])
    assert "/Users/" not in json.dumps(result)


def test_native_health_and_new_start_use_same_gate(capture_env):
    fixture, settings, _ = capture_env
    client, headers, _, sessions, _ = fixture
    policy = native(settings)
    path = settings.model_config_dir / "capture.local.yaml"
    path.write_text(path.read_text() + "stream_domains: []\n")
    policy = load_policy(settings)
    data = {"session_id": str(sessions[0].id), "platform": "douyin",
            "source_ref": "https://live.douyin.com/12345"}
    with ready(settings, policy):
        health = client.get("/api/v1/capture/health").json()
        provider = health["providers"]["douyin"]
        assert health["execution"]["ready"] and provider["dependencies_ready"]
        assert not provider["start_ready"]
        response = client.post("/api/v1/capture/runs", json=data,
                               headers=headers | {"Idempotency-Key": "blocked"})
        assert response.status_code == 503
        assert response.json()["code"] == "capture_source_access_not_configured"


def test_idempotent_retry_survives_new_policy_block(capture_env):
    fixture, settings, _ = capture_env
    client, headers, _, _, _ = fixture
    policy = native(settings)
    with ready(settings, policy):
        run, data = start_run(fixture, key="preserve")
    path = settings.model_config_dir / "capture.local.yaml"
    path.write_text(path.read_text() + "stream_domains: []\n")
    response = client.post("/api/v1/capture/runs", json=data,
                           headers=headers | {"Idempotency-Key": "preserve"})
    assert response.status_code == 202
    assert response.json()["capture_run_id"] == run["capture_run_id"]


def test_media_tools_and_platform_allowlist_match_api(capture_env):
    fixture, settings, _ = capture_env
    client, headers, _, sessions, _ = fixture
    native(settings)
    path = settings.model_config_dir / "capture.local.yaml"
    path.write_text(
        path.read_text() + "ffprobe: /nonexistent/ffprobe\nallowed_platforms: [douyin]\n"
    )
    policy = load_policy(settings)
    data = {"session_id": str(sessions[0].id), "platform": "douyin",
            "source_ref": "https://live.douyin.com/12345"}
    with ready(settings, policy):
        health = client.get("/api/v1/capture/health").json()
        assert not health["providers"]["douyin"]["start_ready"]
        response = client.post("/api/v1/capture/runs", json=data,
                               headers=headers | {"Idempotency-Key": "missing-media"})
        assert response.status_code == 503
        assert response.json()["code"] == "capture_media_tools_missing"
        assert "capture_platform_disabled" in {
            b["code"] for b in health["providers"]["wechat"]["blockers"]
        }


def test_configured_ready_does_not_claim_platform_verified(capture_env):
    _, settings, _ = capture_env
    policy = native(settings)
    result = platform_conditions(policy, "douyin", ONLINE, True, True)
    assert result["start_ready"] and not result["blockers"]
    assert not result["real_platform_verified"]


def test_disabled_platform_cannot_use_probe_or_operator_start(capture_env):
    fixture, settings, _ = capture_env
    client, headers, _, sessions, _ = fixture
    path = settings.model_config_dir / "capture.local.yaml"
    path.write_text(path.read_text() + "allowed_platforms: [douyin]\n")
    data = {"platform": "wechat", "source_ref": "phone_cast"}
    response = client.post("/api/v1/capture/probe", json=data, headers=headers)
    assert response.status_code == 503 and response.json()["code"] == "capture_platform_disabled"
    response = client.post(
        "/api/v1/capture/runs", json=data | {"session_id": str(sessions[0].id)},
        headers=headers | {"Idempotency-Key": "disabled-platform"},
    )
    assert response.status_code == 503 and response.json()["code"] == "capture_platform_disabled"
