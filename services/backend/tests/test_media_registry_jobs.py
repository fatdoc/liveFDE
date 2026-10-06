"""Registry bridge contracts: no DB and no network required for these checks."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from live_review.core.provider_config import ProviderConfigError
from live_review.integrations.asr import create_asr_adapter
from live_review.integrations.media import MediaError
from live_review.workers.media_configuration import (
    config_environment,
    execution_environment,
    prepare_configuration,
    restore_configuration,
)

ROOT = Path(__file__).resolve().parents[3]


def legacy(tmp_path):
    path = tmp_path / "legacy.yaml"
    path.write_text((ROOT / "infra/providers.offline.example.yaml").read_text())
    return path


def test_v1_roundtrip_unchanged_and_no_implicit_migration(tmp_path):
    settings = SimpleNamespace(environment="development")
    path = legacy(tmp_path)
    captured, execution, locator = prepare_configuration(settings, config_path=path)
    data = {
        "provider_snapshot": captured.model_dump(mode="json"),
        **locator,
        "allow_network": False,
    }
    restored, route = restore_configuration(data, settings)
    assert captured == restored and execution == route
    assert data["provider_snapshot"]["snapshot_version"] == 1
    assert set(locator) == {"provider_config_path"}
    assert execution_environment(data, settings) == "development"
    with pytest.raises(MediaError, match="legacy_configuration_options_invalid"):
        prepare_configuration(settings, config_path=path, model_id="asr.default")
    path.write_text(path.read_text().replace("timeout_seconds: 60", "timeout_seconds: 61"))
    with pytest.raises(ProviderConfigError, match="configuration_changed"):
        restore_configuration(data, settings)


@pytest.mark.parametrize(
    "runtime,selected,expected",
    [
        ("development", None, "development"),
        ("development", "test", "test"),
        ("production", None, "production"),
        ("production", "staging", "staging"),
    ],
)
def test_environment_mapping(runtime, selected, expected):
    assert config_environment(SimpleNamespace(environment=runtime), selected) == expected


@pytest.mark.parametrize(
    "runtime,selected",
    [
        ("production", "development"),
        ("production", "test"),
        ("development", "staging"),
        ("development", "production"),
        ("development", "bogus"),
        ("staging", None),
    ],
)
def test_environment_cannot_downgrade_or_reinterpret_runtime(runtime, selected):
    with pytest.raises(MediaError):
        config_environment(SimpleNamespace(environment=runtime), selected)


def test_factory_enforces_capability_and_network_flag(tmp_path, monkeypatch):
    captured, execution, _ = prepare_configuration(
        SimpleNamespace(environment="development"), config_path=legacy(tmp_path)
    )
    fixture = {"segments": {}}
    adapter = create_asr_adapter(
        execution, media=captured.content.media, fixture_payload=fixture, environment="test"
    )
    assert adapter.synthetic
    with pytest.raises(MediaError, match="offline_fixture_not_allowed"):
        create_asr_adapter(
            execution,
            media=captured.content.media,
            fixture_payload=fixture,
            environment="production",
        )
    with pytest.raises(MediaError, match="model_capability_mismatch"):
        create_asr_adapter(
            execution.model_copy(update={"capability": "text"}),
            media=captured.content.media,
            environment="test",
        )


def test_legacy_submit_only_persists_public_configuration(tmp_path, monkeypatch):
    from live_review.workers import media_jobs

    settings = SimpleNamespace(environment="development", storage_root=tmp_path / "storage")
    db = Mock()
    db.scalar.return_value = object()
    monkeypatch.setattr(
        media_jobs,
        "material_source",
        lambda *args: (None, SimpleNamespace(sha256="a" * 64, size_bytes=100)),
    )
    received = []
    monkeypatch.setattr(media_jobs, "create_job", lambda *args: received.append(args[-1]))
    media_jobs.submit(
        db,
        settings,
        workspace_id="workspace",
        actor_id="actor",
        material_id="material",
        config_path=legacy(tmp_path),
        fixture_payload={"segments": {}},
    )
    data = received[0]
    assert data["kind"] == "media_transcription_v1"
    assert data["provider_snapshot"]["snapshot_version"] == 1
    assert not data["allow_network"]
    assert "api_key" not in json.dumps(data)
    db.commit.assert_not_called()


def test_unknown_snapshot_versions_are_rejected():
    with pytest.raises(MediaError, match="configuration_snapshot_version_unsupported"):
        restore_configuration(
            {"provider_snapshot": {"snapshot_version": 3}},
            SimpleNamespace(environment="development"),
        )


def registry_files(tmp_path, remote=False):
    root = tmp_path / "config"
    root.mkdir()
    route = (
        "      protocol: openai_compatible\n      operation: audio_transcriptions\n"
        "      provider: example\n      model: speech-v1\n"
        "      base_url: https://example.invalid/v1\n      key_env: SYNTHETIC_JOB_API_KEY\n"
        "      max_requests: 3\n      max_cost_usd: 1.0\n"
        if remote
        else (
            "      protocol: offline_fixture\n      provider: synthetic\n"
            "      model: fixture-v1\n      max_requests: 3\n"
        )
    )
    (root / "models.yaml").write_text(
        "revision: jobs-v2\nmedia: {segment_seconds: 1}\n"
        "models:\n  speech:\n    capability: asr\n    route:\n      enabled: true\n"
        + route
        + "aliases:\n  asr.default: speech\n"
    )
    return root


def test_v2_roundtrip_default_locator_missing_optional_files(tmp_path):
    root = registry_files(tmp_path)
    settings = SimpleNamespace(environment="development")
    captured, execution, locator = prepare_configuration(settings, config_dir=root)
    data = {
        "provider_snapshot": captured.model_dump(mode="json"),
        **locator,
        "allow_network": False,
    }
    restored, reloaded = restore_configuration(data, settings)
    assert captured.snapshot_version == 2 and captured == restored
    assert execution == reloaded
    assert data["model_id"] == "asr.default"
    assert not data["provider_config_options"]["local_explicit"]
    assert not data["provider_config_options"]["dotenv_explicit"]
    (root / "local.yaml").write_text("media: {max_duration_seconds: 1000}")
    with pytest.raises(MediaError, match="configuration_locator_changed"):
        restore_configuration(data, settings)


def test_v2_dotenv_credentials_private_and_per_job_authorization(tmp_path, monkeypatch):
    import os

    root = registry_files(tmp_path, remote=True)
    monkeypatch.delenv("SYNTHETIC_JOB_API_KEY", raising=False)
    secret = "synthetic-private-job-credential"
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"SYNTHETIC_JOB_API_KEY={secret}\nLIVE_DATABASE_URL=ignored-database\n")
    dotenv.chmod(0o600)
    before = dict(os.environ)
    settings = SimpleNamespace(environment="development")
    with pytest.raises(ProviderConfigError, match="network_not_authorized"):
        prepare_configuration(settings, config_dir=root)
    captured, execution, locator = prepare_configuration(
        settings, config_dir=root, allow_network=True
    )
    data = {"provider_snapshot": captured.model_dump(mode="json"), **locator, "allow_network": True}
    assert execution.api_key.get_secret_value() == secret
    assert secret not in json.dumps(data) and "ignored-database" not in json.dumps(data)
    assert dict(os.environ) == before
    assert restore_configuration(data, settings)[1].api_key.get_secret_value() == secret
    with pytest.raises(ProviderConfigError, match="network_not_authorized"):
        restore_configuration(data | {"allow_network": False}, settings)
    dotenv.write_text("SYNTHETIC_JOB_API_KEY=synthetic-rotated-key\n")
    restored, execution = restore_configuration(data, settings)
    assert restored.config_hash == captured.config_hash
    assert execution.api_key.get_secret_value() == "synthetic-rotated-key"


def test_v2_environment_fixed_and_llm_cannot_route_to_asr(tmp_path):
    root = registry_files(tmp_path)
    settings = SimpleNamespace(environment="development")
    captured, _, locator = prepare_configuration(settings, config_dir=root)
    data = {
        "provider_snapshot": captured.model_dump(mode="json"),
        **locator,
        "allow_network": False,
    }
    with pytest.raises(MediaError, match="runtime_environment_changed"):
        restore_configuration(data, SimpleNamespace(environment="production"))
    with pytest.raises(MediaError, match="model_capability_mismatch"):
        prepare_configuration(settings, config_dir=root, model_id="llm.default")
    with pytest.raises(MediaError, match="configuration_environment_downgrade"):
        prepare_configuration(
            SimpleNamespace(environment="production"), config_dir=root, config_env="development"
        )


def test_staging_real_route_requires_production_runtime_and_explicit_dotenv(tmp_path, monkeypatch):
    root = registry_files(tmp_path, remote=True)
    monkeypatch.delenv("SYNTHETIC_JOB_API_KEY", raising=False)
    dotenv = tmp_path / ".env"
    dotenv.write_text("SYNTHETIC_JOB_API_KEY=synthetic-staging-credential\n")
    dotenv.chmod(0o600)
    (root / "local.yaml").write_text("invalid_field: ignored_in_staging\n")
    settings = SimpleNamespace(environment="production")
    with pytest.raises(ProviderConfigError, match="provider_credential_unavailable"):
        prepare_configuration(settings, config_dir=root, config_env="staging", allow_network=True)
    captured, execution, metadata = prepare_configuration(
        settings, config_dir=root, config_env="staging", dotenv_path=dotenv, allow_network=True
    )
    data = {
        "provider_snapshot": captured.model_dump(mode="json"),
        **metadata,
        "allow_network": True,
    }
    assert captured.content.environment == "staging"
    assert execution_environment(data, settings) == "production"
    assert restore_configuration(data, settings)[0] == captured
    assert execution.api_key.get_secret_value() == "synthetic-staging-credential"
    with pytest.raises(MediaError, match="configuration_environment_runtime_mismatch"):
        prepare_configuration(
            SimpleNamespace(environment="development"),
            config_dir=root,
            config_env="staging",
            dotenv_path=dotenv,
            allow_network=True,
        )


def test_v2_submit_keeps_credentials_out_of_payload_and_settings(tmp_path, monkeypatch):
    from live_review.workers import media_jobs

    root = registry_files(tmp_path, remote=True)
    monkeypatch.delenv("SYNTHETIC_JOB_API_KEY", raising=False)
    dotenv = tmp_path / ".env"
    dotenv.write_text("SYNTHETIC_JOB_API_KEY=synthetic-submit-secret\n")
    dotenv.chmod(0o600)
    settings = SimpleNamespace(environment="development", storage_root=tmp_path / "storage")
    db = Mock()
    db.scalar.return_value = object()
    monkeypatch.setattr(
        media_jobs,
        "material_source",
        lambda *args: (None, SimpleNamespace(sha256="a" * 64, size_bytes=100)),
    )
    received = []
    monkeypatch.setattr(media_jobs, "create_job", lambda *args: received.append(args[-1]))
    client = Mock(side_effect=AssertionError("No HTTP client should be opened at submit"))
    monkeypatch.setattr("live_review.integrations.asr.compatible.httpx.Client", client)
    media_jobs.submit(
        db,
        settings,
        workspace_id="workspace",
        actor_id="actor",
        material_id="material",
        config_dir=root,
        allow_network=True,
    )
    assert received[0]["provider_snapshot"]["snapshot_version"] == 2
    assert "synthetic-submit-secret" not in json.dumps(received[0]) + repr(settings)
    assert "api_key" not in json.dumps(received[0])
    client.assert_not_called()


@pytest.mark.parametrize(
    "runtime,alias,canonical",
    [
        ("development", "dev", "development"),
        ("production", "prod", "production"),
    ],
)
def test_environment_aliases_normalized_before_policy(runtime, alias, canonical):
    assert config_environment(SimpleNamespace(environment=runtime), alias) == canonical


def test_production_dev_alias_cannot_downgrade():
    with pytest.raises(MediaError, match="configuration_environment_downgrade"):
        config_environment(SimpleNamespace(environment="production"), "dev")


@pytest.mark.parametrize("alias", ["dev", "prod"])
def test_operator_parser_accepts_config_environment_alias(alias, monkeypatch):
    from uuid import uuid4

    from live_review.workers import media_operator

    class Parsed(Exception):
        pass

    def after_parse():
        raise Parsed

    monkeypatch.setattr(media_operator, "get_settings", after_parse)
    # Reaching Settings proves argparse accepted the alias, without opening a DB.
    with pytest.raises(Parsed):
        media_operator.main(
            [
                "submit",
                "--workspace-id",
                str(uuid4()),
                "--admin-id",
                str(uuid4()),
                "--material-id",
                str(uuid4()),
                "--config-dir",
                "/synthetic/config",
                "--config-env",
                alias,
            ]
        )
