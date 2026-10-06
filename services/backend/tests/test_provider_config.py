"""Security and retry semantics for YAML-only provider policy; never contact vendors."""

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from live_review.core.provider_config import (
    MAX_BYTES,
    ProviderConfig,
    ProviderConfigError,
    load_config,
    resolve_execution,
    restore_snapshot,
    snapshot,
)

ROOT = Path(__file__).resolve().parents[3]


def load_text(tmp_path, text, **kwargs):
    path = tmp_path / "providers.yaml"
    path.write_text(text)
    return load_config(path, **kwargs)


def fixture_config():
    return load_config(ROOT / "infra/providers.offline.example.yaml")


def test_default_disabled_and_offline_explicit():
    config = load_config(ROOT / "infra/providers.example.yaml", environment="production")
    for name in ("asr", "text", "vision"):
        with pytest.raises(ProviderConfigError, match="provider_unconfigured"):
            resolve_execution(snapshot(config), name, config, environment="production")
    offline = fixture_config()
    resolved = resolve_execution(snapshot(offline), "asr", offline, environment="test")
    assert resolved.synthetic is True
    assert resolved.api_key is None
    assert "api_key" not in resolved.model_dump()
    with pytest.raises(ProviderConfigError, match="synthetic_forbidden"):
        load_config(ROOT / "infra/providers.offline.example.yaml", environment="production")
    with pytest.raises(ProviderConfigError, match="synthetic_forbidden"):
        resolve_execution(snapshot(offline), "asr", offline, environment="production")


@pytest.mark.parametrize(
    "text",
    [
        "revision: x\nrevision: y",
        "revision: x\nproviders: {asr: {enabled: false, enabled: true}}",
        "revision: !!str secret-value",
        "!!python/object/apply:os.system ['echo never']",
        "revision: &name x\nother: *name",
        "revision: x\nother: " + "[" * 20 + "0" + "]" * 20,
        "revision: x\napi_key: secret-value",
        "revision: x\nproviders: {asr: {password: secret-value}}",
        "revision: x\nmedia: {sample_rate: 44100}",
        "revision: x\nmedia: {channels: 2}",
        "revision: x\nmedia: {segment_seconds: 0}",
        "revision: x\nmedia: {segment_seconds: '10'}",
        "revision: x\nproviders: {asr: {max_cost_usd: .inf}}",
        "revision: x\nproviders: {asr: {max_cost_usd: .nan}}",
        "revision: x\nproviders: {asr: {timeout_seconds: -1}}",
        "revision: x\nproviders: {asr: {key_env: '${SECRET}'}}",
        "revision: x\n---\nrevision: y",
        "{[bad]: value}",
    ],
)
def test_unsafe_yaml_and_values_rejected_without_echo(tmp_path, text):
    with pytest.raises(ProviderConfigError) as exc:
        load_text(tmp_path, text)
    assert "secret-value" not in str(exc.value)
    assert "never" not in str(exc.value)


def test_complexity_size_and_paths(tmp_path):
    with pytest.raises(ProviderConfigError, match="too_large"):
        load_text(tmp_path, "#" * (MAX_BYTES + 1))
    with pytest.raises(ProviderConfigError, match="complexity"):
        load_text(tmp_path, "items: [" + "0," * 2200 + "]")
    target = tmp_path / "real.yaml"
    target.write_text("revision: x")
    link = tmp_path / "link.yaml"
    link.symlink_to(target)
    for path in (link, Path("relative.yaml"), Path("https://invalid/x.yaml"), tmp_path):
        with pytest.raises(ProviderConfigError):
            load_config(path)


def test_snapshot_roundtrip_immutable_and_canonical(tmp_path):
    first = load_text(tmp_path, "revision: same\nproviders: {asr: {enabled: false}}")
    second = load_text(tmp_path, "providers: {asr: {protocol: disabled}}\nrevision: same\n")
    captured = snapshot(first)
    assert captured.config_hash == snapshot(second).config_hash
    restored = restore_snapshot(json.loads(captured.model_dump_json()))
    assert restored == captured
    with pytest.raises(ValidationError):
        captured.content.providers.asr.enabled = True
    with pytest.raises(ValidationError):
        captured.content.media.segment_seconds = 9
    dumped = captured.model_dump(mode="json")
    dumped["content"]["revision"] = "mutated"
    assert captured.content.revision == "same"
    with pytest.raises(ProviderConfigError, match="invalid_config_snapshot"):
        restore_snapshot(dumped)


def test_retry_rejects_route_budget_or_media_change():
    original = fixture_config()
    captured = snapshot(original)
    for section, field, value in [
        ("media", "segment_seconds", 1),
        ("asr", "max_requests", 2),
        ("asr", "timeout_seconds", 3),
    ]:
        data = original.model_dump()
        target = data["media"] if section == "media" else data["providers"][section]
        target[field] = value
        changed = ProviderConfig.model_validate(data)
        with pytest.raises(ProviderConfigError, match="configuration_changed"):
            resolve_execution(captured, "asr", changed, environment="test")


def remote_data():
    return {
        "revision": "explicit-route",
        "providers": {
            "asr": {
                "enabled": True,
                "protocol": "openai_compatible",
                "operation": "audio_transcriptions",
                "provider": "example",
                "model": "example-model",
                "base_url": "https://example.invalid/v1",
                "key_env": "EXAMPLE_API_KEY",
                "max_requests": 1,
                "max_cost_usd": 1.0,
            }
        },
    }


def test_real_protocol_requires_explicit_authorization_before_secret_resolution():
    class ForbiddenEnvironment(dict):
        def get(self, key, default=None):
            raise AssertionError("must not resolve any real credential")

    config = ProviderConfig.model_validate(remote_data())
    captured = snapshot(config)
    assert "EXAMPLE_API_KEY" in captured.model_dump_json()
    with pytest.raises(ProviderConfigError, match="network_not_authorized"):
        resolve_execution(
            captured, "asr", config, environment="production", environ=ForbiddenEnvironment()
        )
    with pytest.raises(ProviderConfigError, match="provider_unconfigured"):
        resolve_execution(captured, "text", config, environment="production")


@pytest.mark.parametrize(
    "url",
    [
        "http://example.invalid",
        "https://user:secret@example.invalid",
        "https://example.invalid?key=secret",
        "https://example.invalid/#secret",
        "https://example.invalid:8443/v1",
        "https://example.invalid/${SECRET}",
        "https://example.invalid/../v1",
        "https://example.invalid/%2e%2e",
        "file:///etc/secret",
    ],
)
def test_endpoint_credentials_interpolation_and_unsafe_routes_rejected(url):
    data = copy.deepcopy(remote_data())
    data["providers"]["asr"]["base_url"] = url
    with pytest.raises(ValidationError):
        ProviderConfig.model_validate(data)


def test_snapshot_copy_cannot_bypass_execution_integrity():
    config = fixture_config()
    altered = config.model_copy(update={"revision": "changed"})
    forged = snapshot(config).model_copy(update={"content": altered})
    with pytest.raises(ProviderConfigError, match="invalid_config_snapshot"):
        resolve_execution(forged, "asr", config, environment="test")


def test_boolean_not_accepted_as_channel_count(tmp_path):
    with pytest.raises(ProviderConfigError):
        load_text(tmp_path, "revision: x\nmedia: {channels: true}")


def test_authorized_asr_resolves_secret_only_in_memory():
    config = ProviderConfig.model_validate(remote_data())
    captured = snapshot(config)
    route = resolve_execution(
        captured,
        "asr",
        config,
        environment="production",
        allow_network=True,
        environ={"EXAMPLE_API_KEY": "synthetic-secret"},
    )
    assert route.synthetic is False
    assert route.api_key.get_secret_value() == "synthetic-secret"
    assert "synthetic-secret" not in repr(route)
    assert "synthetic-secret" not in route.model_dump_json()
    assert "synthetic-secret" not in captured.model_dump_json()
    with pytest.raises(ProviderConfigError, match="credential_unavailable") as exc:
        resolve_execution(
            captured,
            "asr",
            config,
            environment="production",
            allow_network=True,
            environ={"EXAMPLE_API_KEY": "secret\ninvalid"},
        )
    assert "secret" not in str(exc.value)


def test_inactive_profile_retained_without_activation():
    data = remote_data()
    data["providers"]["asr"]["enabled"] = False
    config = ProviderConfig.model_validate(data)
    assert config.providers.asr.model == "example-model"
    with pytest.raises(ProviderConfigError, match="provider_unconfigured"):
        resolve_execution(
            snapshot(config),
            "asr",
            config,
            environment="production",
            allow_network=True,
            environ={"EXAMPLE_API_KEY": "test-only"},
        )


def test_audio_operation_required_and_no_text_fallback():
    data = remote_data()
    data["providers"]["asr"].pop("operation")
    with pytest.raises(ValidationError):
        ProviderConfig.model_validate(data)
    data = remote_data()
    data["providers"]["text"] = data["providers"].pop("asr")
    config = ProviderConfig.model_validate(data)
    with pytest.raises(ProviderConfigError, match="provider_protocol_unsupported"):
        resolve_execution(
            snapshot(config),
            "text",
            config,
            environment="production",
            allow_network=True,
            environ={"EXAMPLE_API_KEY": "test-only"},
        )
