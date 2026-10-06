import json

import pytest
from pydantic import ValidationError

from live_review.core.model_config import load_model_config
from live_review.core.model_registry import ModelRegistry, restore_snapshot
from live_review.core.provider_config import ProviderConfigError


@pytest.fixture
def registry(tmp_path):
    root = tmp_path / "config"
    root.mkdir()
    (root / "models.yaml").write_text("""revision: fixture-v2
models:
  audio_one:
    capability: asr
    route:
      enabled: true
      protocol: openai_compatible
      operation: audio_transcriptions
      provider: example
      model: audio-model
      base_url: https://example.invalid/v1
      key_env: SYNTHETIC_API_KEY
      max_requests: 2
      max_cost_usd: 1.0
aliases:
  asr.default: audio_one
""")
    return root, ModelRegistry(
        load_model_config(
            root, environment="test", environ={"SYNTHETIC_API_KEY": "synthetic-private-value"}
        )
    )


def test_get_immutable_description_and_validate_references(registry):
    _, model_registry = registry
    model = model_registry.get("asr.default")
    assert model.name == "audio_one" and model.capability == "asr"
    with pytest.raises(ValidationError):
        model.route.model = "mutate"
    assert model_registry.get("llm.default").capability == "llm"
    assert model_registry.validate_references(["asr.default"], "asr") == (model,)
    with pytest.raises(ProviderConfigError, match="capability_mismatch"):
        model_registry.validate_references(["llm.default"], "asr")
    with pytest.raises(ProviderConfigError, match="not_registered"):
        model_registry.get("missing")


def test_resolve_requires_authorization_secrets_never_dumped(registry, monkeypatch):
    _, model_registry = registry
    loaded_type = type(model_registry.loaded)
    original = loaded_type.credential
    calls = []

    def credential(self, name):
        calls.append(name)
        return original(self, name)

    monkeypatch.setattr(loaded_type, "credential", credential)
    with pytest.raises(ProviderConfigError, match="network_not_authorized"):
        model_registry.resolve("asr.default")
    assert calls == []
    execution = model_registry.resolve("asr.default", allow_network=True)
    assert calls == ["SYNTHETIC_API_KEY"]
    assert execution.api_key.get_secret_value() == "synthetic-private-value"
    for value in (model_registry.loaded, model_registry.snapshot(), execution):
        assert "synthetic-private-value" not in repr(value) + value.model_dump_json()
    with pytest.raises(ProviderConfigError, match="not_executable"):
        model_registry.resolve("llm.default", allow_network=True)


def test_snapshot_roundtrip_and_retry_full_config_fingerprint(registry):
    root, model_registry = registry
    captured = model_registry.snapshot()
    restored = restore_snapshot(json.loads(captured.model_dump_json()))
    assert restored == captured
    assert restored.snapshot_version == 2
    changed = captured.model_dump(mode="json")
    changed["content"]["media"]["segment_seconds"] = 1
    with pytest.raises(ProviderConfigError, match="invalid_model_snapshot"):
        restore_snapshot(changed)
    (root / "local.yaml").write_text("media: {segment_seconds: 1}")
    next_registry = ModelRegistry(load_model_config(root, environment="test", environ={}))
    with pytest.raises(ProviderConfigError, match="configuration_changed"):
        next_registry.resolve("asr.default", captured=captured)


def test_secret_rotation_not_part_of_public_fingerprint(registry):
    root, model_registry = registry
    second = ModelRegistry(
        load_model_config(
            root, environment="test", environ={"SYNTHETIC_API_KEY": "different-synthetic-key"}
        )
    )
    assert second.snapshot().config_hash == model_registry.snapshot().config_hash
    result = second.resolve("asr.default", captured=model_registry.snapshot(), allow_network=True)
    assert result.api_key.get_secret_value() == "different-synthetic-key"


def test_descriptive_models_and_typed_parameters(registry):
    root, _ = registry
    (root / "local.yaml").write_text("""models:
  embedding_example:
    capability: embedding
    route: {enabled: false, protocol: disabled}
    parameters: {device: cpu, model_path: models/embedding-placeholder}
  reranker_example:
    capability: reranker
    route: {enabled: false, protocol: disabled}
    parameters: {device: cuda:0, model_path: models/reranker-placeholder}
  detection_example:
    capability: detection
    route: {enabled: false, protocol: disabled}
    parameters: {device: cpu, confidence: 0.5}
  llm_unconfigured:
    parameters: {temperature: 0.2}
aliases:
  embedding.default: embedding_example
  reranker.default: reranker_example
  detection.default: detection_example
""")
    registry = ModelRegistry(load_model_config(root, environment="test", environ={}))
    for capability in ("embedding", "reranker", "detection"):
        assert registry.get(f"{capability}.default").capability == capability
        with pytest.raises(ProviderConfigError, match="not_executable"):
            registry.resolve(f"{capability}.default", allow_network=True)
    assert registry.get("llm.default").parameters.temperature == 0.2
    assert (
        restore_snapshot(json.loads(registry.snapshot().model_dump_json())) == registry.snapshot()
    )


@pytest.mark.parametrize(
    "params", ["{temperature: 0.1}", "{device: cpu}", "{model_path: models/x}"]
)
def test_asr_parameters_never_silently_ignored(registry, params):
    root, _ = registry
    (root / "local.yaml").write_text(f"models: {{audio_one: {{parameters: {params}}}}}")
    with pytest.raises(ProviderConfigError):
        load_model_config(root, environment="test", environ={})


@pytest.mark.parametrize(
    "params",
    [
        "{temperature: 2.1}",
        "{temperature: .nan}",
        "{confidence: 0.5}",
        "{model_path: ../escape}",
        "{device: auto}",
    ],
)
def test_parameter_bounds_and_capability_are_validated(registry, params):
    root, _ = registry
    (root / "local.yaml").write_text(f"models: {{llm_unconfigured: {{parameters: {params}}}}}")
    with pytest.raises(ProviderConfigError):
        load_model_config(root, environment="test", environ={})
