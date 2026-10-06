import os

import pytest

from live_review.core.model_config import deep_merge, load_model_config
from live_review.core.provider_config import ProviderConfigError


@pytest.fixture
def config_dir(tmp_path):
    root = tmp_path / "config"
    root.mkdir()
    (root / "environments").mkdir()
    (root / "models.yaml").write_text("revision: fixture-v2\nmedia: {segment_seconds: 10}")
    return root


def test_layer_order_no_input_mutation_and_provenance(config_dir):
    (config_dir / "environments/development.yaml").write_text("media: {segment_seconds: 20}")
    (config_dir / "local.yaml").write_text("media: {segment_seconds: 30}")
    dot = config_dir.parent / ".env"
    dot.write_text("LIVE_MODEL_SEGMENT_SECONDS=40\nUNRELATED_SECRET=synthetic-secret\n")
    dot.chmod(0o600)
    before = dict(os.environ)
    loaded = load_model_config(
        config_dir, environment="dev", environ={"LIVE_MODEL_SEGMENT_SECONDS": "50"}
    )
    assert loaded.public.media.segment_seconds == 50
    assert os.environ == before
    assert "synthetic-secret" not in repr(loaded) + loaded.model_dump_json()
    source = next(p for p in loaded.provenance if p.field_path == "media.segment_seconds")
    assert source.source == "environment"
    assert "50" not in repr(source)
    assert loaded.source_locator()["dotenv_path"] == str(dot)
    assert loaded.source_locator()["local_path"] == str(config_dir / "local.yaml")
    without_system = load_model_config(config_dir, environment="development", environ={})
    assert without_system.public.media.segment_seconds == 40
    base, overlay = {"x": {"a": [1], "b": 2}}, {"x": {"a": [3], "b": None}}
    result = deep_merge(base, overlay)
    assert result == {"x": {"a": [3], "b": None}}
    assert base == {"x": {"a": [1], "b": 2}} and overlay["x"]["a"] == [3]


def test_production_staging_ignore_local_and_implicit_dotenv(config_dir):
    (config_dir / "local.yaml").write_text("api_key: forbidden")
    dot = config_dir.parent / ".env"
    dot.write_text("LIVE_MODEL_SEGMENT_SECONDS=40")
    for env in ("prod", "production", "staging"):
        loaded = load_model_config(config_dir, environment=env, environ={})
        assert loaded.public.media.segment_seconds == 10
        assert loaded.source_locator()["local_path"] is None
        assert loaded.source_locator()["dotenv_path"] is None
        with pytest.raises(ProviderConfigError, match="local_overlay_forbidden"):
            load_model_config(
                config_dir, environment=env, local_path=config_dir / "local.yaml", environ={}
            )
    with pytest.raises(ProviderConfigError):
        load_model_config(config_dir, environment="production", dotenv_path=dot, environ={})
    dot.chmod(0o600)
    loaded = load_model_config(config_dir, environment="production", dotenv_path=dot, environ={})
    assert loaded.public.media.segment_seconds == 40


@pytest.mark.parametrize(
    "bad",
    [
        "api_key: do-not-echo",
        "models: {hidden: {route: {password: do-not-echo}}}",
        "revision: x\nrevision: y",
        "revision: &x value",
        "revision: !!str value",
        "media: {segment_seconds: .nan}",
        "media: {channels: true}",
        "revision: ${BAD}",
        "media: " + "[" * 15 + "1" + "]" * 15,
    ],
)
def test_invalid_lower_layer_cannot_be_masked_by_local(config_dir, bad):
    (config_dir / "models.yaml").write_text(bad)
    (config_dir / "local.yaml").write_text("revision: corrected")
    with pytest.raises(ProviderConfigError) as exc:
        load_model_config(config_dir, environment="dev", environ={})
    assert "do-not-echo" not in str(exc.value)


@pytest.mark.parametrize(
    "bad",
    [
        "X=$(touch bad)",
        "X=${OTHER}",
        "export X=value",
        "X=one\nX=two",
        "X=`never`",
        "not-an-assignment",
    ],
)
def test_dotenv_never_executes_or_interpolates(config_dir, bad):
    dot = config_dir.parent / ".env"
    dot.write_text(bad)
    dot.chmod(0o600)
    with pytest.raises(ProviderConfigError):
        load_model_config(config_dir, environment="test", environ={})


def test_env_whitelist_and_missing_locator(config_dir):
    loaded = load_model_config(
        config_dir,
        environment="dev",
        environ={"LIVE_DATABASE_URL": "synthetic-do-not-expose", "LIVE_MODEL_UNKNOWN": "ignored"},
    )
    assert loaded.public.media.segment_seconds == 10
    assert "synthetic-do-not-expose" not in loaded.model_dump_json()
    assert loaded.source_locator()["local_path"] is None
    assert loaded.source_locator()["dotenv_path"] is None
    with pytest.raises(ProviderConfigError):
        load_model_config(config_dir, environment="../../production", environ={})


def test_alias_type_and_duplicate_model_names_rejected(config_dir):
    (config_dir / "local.yaml").write_text("aliases: {asr.default: llm_unconfigured}")
    with pytest.raises(ProviderConfigError):
        load_model_config(config_dir, environment="dev", environ={})


@pytest.mark.parametrize(
    "route",
    [
        "{base_url: 'https://user:QA_SENTINEL@example.invalid/v1'}",
        "{base_url: 'https://example.invalid/v1?key=QA_SENTINEL'}",
        "{base_url: 'https://example.invalid/v1#QA_SENTINEL'}",
        "{client_secret: QA_SENTINEL}",
        "{refresh_token: QA_SENTINEL}",
    ],
)
def test_lower_layer_embedded_credentials_cannot_be_hidden_by_null(config_dir, route):
    (config_dir / "models.yaml").write_text(f"models: {{asr_unconfigured: {{route: {route}}}}}")
    (config_dir / "local.yaml").write_text("models: {asr_unconfigured: {route: {base_url: null}}}")
    with pytest.raises(ProviderConfigError) as error:
        load_model_config(config_dir, environment="test", environ={})
    assert "QA_SENTINEL" not in str(error.value)
