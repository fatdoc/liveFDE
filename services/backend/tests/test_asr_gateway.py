"""Policy boundaries and config compatibility, deliberately no real model traffic."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from live_review.core.errors import ApiError
from live_review.core.model_config import load_model_config
from live_review.core.model_registry import ModelRegistry, restore_snapshot
from live_review.core.provider_config import ProviderConfigError
from live_review.integrations.asr_gateway.contracts import (
    ASRError,
    ASRRequest,
    ASRResult,
    ASRSegment,
)
from live_review.integrations.asr_gateway.service import ASRGateway
from live_review.modules.asr.schemas import Authorization, Preferences, SettingsOutput
from live_review.modules.asr.service import authorization


def test_registry_new_routes_do_not_change_old_public_shape(tmp_path):
    (tmp_path / "models.yaml").write_text("schema_version: 2\nrevision: old\n")
    before = ModelRegistry(load_model_config(tmp_path, environment="development", environ={}))
    captured = before.snapshot()
    assert restore_snapshot(captured.model_dump(mode="json")) == captured
    for item in captured.content.models:
        assert "model_root" not in item.route.model_dump()
        assert "secret_id_env" not in item.route.model_dump()
    assert captured.config_hash == before.snapshot().config_hash


def test_named_gateway_route_secrets_remain_private(tmp_path):
    example = Path(__file__).resolve().parents[3] / "config/asr.example.yaml"
    (tmp_path / "models.yaml").write_text(example.read_text())
    registry = ModelRegistry(
        load_model_config(
            tmp_path,
            environment="development",
            environ={
                "TENCENT_SECRET_ID": "synthetic-id",
                "TENCENT_SECRET_KEY": "synthetic-secret",
                "TENCENT_APP_ID": "12345",
                "UNRELATED_PASSWORD": "unrelated-sensitive",
            },
        )
    )
    assert registry.get("asr.local").route.protocol == "local_funasr"
    public = registry.snapshot().model_dump_json() + registry.loaded.model_dump_json()
    assert "synthetic-secret" not in public and "unrelated-sensitive" not in repr(registry.loaded)
    assert len(registry.loaded.credential_values) == 3
    with pytest.raises(ProviderConfigError, match="gateway_execution_required"):
        registry.resolve("asr.local")


def test_preferences_and_grants_are_separate():
    with pytest.raises(ValidationError):
        Preferences(provider="tencent", privacy="local_only")
    cloud = SettingsOutput(provider="tencent", privacy="cloud_allowed", revision=2)
    for grant in (
        Authorization(expected_revision=2),
        Authorization(expected_revision=2, allow_network=True),
    ):
        with pytest.raises(ApiError, match="云识别需要"):
            authorization(cloud, grant)
    valid = Authorization(
        expected_revision=2, allow_network=True, max_requests=1, max_cost_usd=0.01
    )
    assert authorization(cloud, valid)["max_requests"] == 1
    with pytest.raises(ApiError):
        authorization(cloud, valid.model_copy(update={"expected_revision": 1}))
    with pytest.raises(ApiError):
        authorization(SettingsOutput(revision=2), valid)


def test_unified_result_sources_and_unknown_identity():
    result = ASRResult(
        provider="local",
        model="test",
        source="local",
        complete=True,
        duration_ms=100,
        elapsed_ms=2,
        segments=(ASRSegment(id="0", text="你好", start_ms=0, end_ms=100, timestamp_source="vad"),),
    )
    assert result.text == "你好" and result.language is None
    assert result.metadata.timestamp_sources == ("vad",)
    assert result.segments[0].speaker_name is None and result.segments[0].emotion is None
    assert ASRResult.model_validate_json(result.model_dump_json()) == result
    with pytest.raises(ValidationError):
        ASRSegment(id="0", text="x", speaker_name="guessed person")


def test_fallback_requires_grant_and_unknown_never_replays(monkeypatch):
    from live_review.integrations.asr_gateway import service

    calls = []

    class Local:
        async def transcribe_file(self, path, request):
            calls.append(("local", request.allow_network))
            raise ASRError("local_model_busy")

    class Recorder:
        async def file(self, provider, path, request):
            calls.append(("cloud", request.allow_network))
            return "recorded"

    monkeypatch.setattr(service, "create_provider", lambda registry, name: Local())
    req = ASRRequest(request_id="test")
    pref = SettingsOutput(privacy="cloud_allowed", allow_cloud_fallback=True, revision=1)
    no_grant = ASRGateway(None, pref, {}, Recorder())
    with pytest.raises(ASRError):
        asyncio.run(no_grant.transcribe_file(Path("unused"), req))
    assert calls == [("local", False)]
    gateway = ASRGateway(
        None, pref, {"allow_network": True, "max_requests": 1, "max_cost_usd": 0.01}, Recorder()
    )
    assert asyncio.run(gateway.transcribe_file(Path("unused"), req)) == "recorded"

    async def unknown(path, request):
        raise ASRError("unknown", unknown=True)

    monkeypatch.setattr(
        service, "create_provider", lambda registry, name: SimpleNamespace(transcribe_file=unknown)
    )
    calls.clear()
    with pytest.raises(ASRError):
        asyncio.run(gateway.transcribe_file(Path("unused"), req))
    assert calls == []


@pytest.mark.parametrize(
    "code",
    [
        "local_model_config_invalid",
        "local_audio_requires_16k_mono",
        "audio_duration_exceeded",
        "local_mps_unsupported",
    ],
)
def test_request_and_configuration_errors_never_cloud_fallback(monkeypatch, code):
    from live_review.integrations.asr_gateway import service

    calls = []

    async def fail(path, request):
        raise ASRError(code)

    class Recorder:
        async def file(self, *args):
            calls.append("cloud")

    monkeypatch.setattr(
        service, "create_provider", lambda *args: SimpleNamespace(transcribe_file=fail)
    )
    prefs = SettingsOutput(privacy="cloud_allowed", allow_cloud_fallback=True, revision=1)
    gateway = ASRGateway(
        None, prefs, {"allow_network": True, "max_requests": 1, "max_cost_usd": 0.01}, Recorder()
    )
    with pytest.raises(ASRError):
        asyncio.run(gateway.transcribe_file(Path("unused"), ASRRequest(request_id="test")))
    assert calls == []


def test_local_fallback_preference_without_grant_stays_local():
    prefs = SettingsOutput(privacy="cloud_allowed", allow_cloud_fallback=True, revision=1)
    granted = authorization(prefs, Authorization(expected_revision=1))
    assert granted == {"allow_network": False, "max_requests": 0, "max_cost_usd": None}


def test_yaml_workspace_defaults_layered_and_separate_snapshot(tmp_path):
    from live_review.modules.asr.policy import load_policy, policy_snapshot

    (tmp_path / "environments").mkdir()
    (tmp_path / "asr-policy.yaml").write_text(
        "defaults:\n  provider: tencent\n  privacy: cloud_allowed\n  speaker: true\n"
    )
    (tmp_path / "environments/development.asr.yaml").write_text("defaults:\n  emotion: true\n")
    (tmp_path / "asr.local.yaml").write_text("defaults:\n  emotion: false\n")
    settings = SimpleNamespace(
        model_config_dir=tmp_path, environment="development", model_config_environment=None
    )
    defaults = load_policy(settings).defaults
    assert defaults.provider == "tencent" and defaults.speaker and not defaults.emotion
    before = policy_snapshot(settings)
    (tmp_path / "asr.local.yaml").write_text("defaults:\n  emotion: true\n")
    assert policy_snapshot(settings) != before
    production = SimpleNamespace(
        model_config_dir=tmp_path, environment="production", model_config_environment=None
    )
    assert not load_policy(production).defaults.emotion


def test_invalid_policy_reports_safe_code(tmp_path):
    from live_review.modules.asr.policy import load_policy

    (tmp_path / "asr-policy.yaml").write_text("defaults:\n  provider: invalid-private-value\n")
    settings = SimpleNamespace(
        model_config_dir=tmp_path, environment="development", model_config_environment=None
    )
    with pytest.raises(ProviderConfigError, match="^invalid_asr_policy$"):
        load_policy(settings)
