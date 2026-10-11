"""Synthetic credentials and private temp files only; no provider traffic."""

import hashlib
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from live_review.core.auth import current_admin, require_mutation
from live_review.core.errors import ApiError, install_errors
from live_review.integrations.asr_gateway.contracts import ASRError
from live_review.integrations.asr_gateway.factory import create_provider, registry_for
from live_review.modules.asr.policy import policy_snapshot
from live_review.modules.asr.router import router
from live_review.modules.asr.tencent_settings import Input, Store
from live_review.workers.asr_jobs import restore_gateway


@pytest.fixture
def settings(tmp_path, monkeypatch):
    for key in ("TENCENT_SECRET_ID", "TENCENT_SECRET_KEY", "TENCENT_APP_ID"):
        monkeypatch.setenv(key, "123456")
    config = tmp_path / "config"
    config.mkdir()
    sample = Path(__file__).resolve().parents[3] / "config/asr.example.yaml"
    (config / "models.yaml").write_text(
        sample.read_text().replace("enabled: false", "enabled: true")
    )
    return SimpleNamespace(
        storage_root=tmp_path / "media",
        model_config_dir=config,
        model_dotenv_path=None,
        model_config_environment=None,
        environment="development",
    )


def save(store, revision="unconfigured", **kwargs):
    return store.update(Input(expected_revision=revision, **kwargs), revision=revision)


def payload(settings, workspace=None):
    registry = registry_for(settings, workspace)
    value = {
        "provider_snapshot": registry.snapshot().model_dump(mode="json"),
        "gateway_policy_snapshot": policy_snapshot(settings),
        "provider_locator": registry.loaded.source_locator(),
        "runtime_environment": settings.environment,
        "storage_fingerprint": hashlib.sha256(str(settings.storage_root).encode()).hexdigest(),
        "preferences": {"provider": "tencent"},
        "authorization": {"allow_network": True},
    }
    if workspace is not None:
        value.update(
            use_workspace_tencent=True,
            workspace_asr_id=str(workspace),
            workspace_asr_revision=registry.loaded.public.revision,
        )
    return value


def test_cas_preserve_clear_and_private_modes(settings):
    store = Store(settings, uuid4())
    first = save(store, secret_id="synthetic-id", secret_key="synthetic-key", app_id="12345")
    assert first.configured and first.app_id_configured and not first.network_checked
    with pytest.raises(ApiError) as error:
        save(store, secret_key="other")
    assert error.value.code == "revision_conflict"
    second = save(store, first.revision, secret_id="replacement-id", model="16k_en")
    assert store.read().secret_key.get_secret_value() == "synthetic-key"
    assert second.configured and second.model == "16k_en"
    public = second.model_dump_json() + repr(store.read())
    for secret in ("synthetic-id", "synthetic-key", "replacement-id", "12345"):
        assert secret not in public
    cleared = store.update(revision=second.revision)
    assert not cleared.configured and not cleared.app_id_configured
    assert cleared.model == "16k_en" and cleared.revision != "unconfigured"
    assert store.read().secret_key.get_secret_value() == ""
    assert store.files.path.stat().st_mode & 0o777 == 0o700
    assert (store.files.path / "tencent.json").stat().st_mode & 0o777 == 0o600


def test_isolation_global_never_used_by_new_workspace(settings):
    a, b = uuid4(), uuid4()
    # Legacy no-workspace callers retain pre-existing registered credentials.
    assert create_provider(registry_for(settings), "tencent") is not None
    with pytest.raises(ASRError, match="asr_provider_disabled"):
        create_provider(registry_for(settings, b), "tencent")
    store = Store(settings, a)
    first = save(store, secret_id="workspace-id", secret_key="workspace-key")
    registry = registry_for(settings, a)
    provider = create_provider(registry, "tencent")
    assert provider is not None  # AppID is not required for file recognition.
    public = registry.snapshot().model_dump_json() + registry.loaded.model_dump_json()
    assert "workspace-key" not in public and "workspace-id" not in public
    assert registry.snapshot().config_hash != registry_for(settings, b).snapshot().config_hash
    store.update(revision=first.revision)
    with pytest.raises(ASRError, match="asr_provider_disabled"):
        create_provider(registry_for(settings, a), "tencent")


def test_worker_checks_workspace_and_key_rotation(settings):
    workspace = uuid4()
    store = Store(settings, workspace)
    first = save(store, secret_id="test-id", secret_key="old-key")
    captured = payload(settings, workspace)
    assert restore_gateway(captured, settings, workspace)
    for wrong in (None, uuid4()):
        with pytest.raises(ASRError, match="configuration_changed"):
            restore_gateway(captured, settings, wrong)
    second = save(store, first.revision, secret_key="new-key")
    with pytest.raises(ASRError, match="configuration_changed"):
        restore_gateway(captured, settings, workspace)
    newer = payload(settings, workspace)
    store.update(revision=second.revision)
    with pytest.raises(ASRError, match="configuration_changed"):
        restore_gateway(newer, settings, workspace)


def test_legacy_tombstone_rejects_cloud_but_local_survives(settings):
    workspace = uuid4()
    old = payload(settings)
    assert restore_gateway(old, settings, workspace)
    Store(settings, workspace).update(revision="unconfigured")
    with pytest.raises(ASRError, match="configuration_changed"):
        restore_gateway(old, settings, workspace)
    old["preferences"] = {"provider": "local", "allow_cloud_fallback": False}
    assert restore_gateway(old, settings, workspace)


@pytest.mark.parametrize(
    "field,value",
    [
        ("secret_key", ""),
        ("secret_id", "a\nb"),
        ("app_id", "invalid"),
        ("model", "other"),
        ("timeout_seconds", 0),
    ],
)
def test_invalid_inputs(field, value):
    with pytest.raises(ValidationError):
        Input(expected_revision="unconfigured", **{field: value})


def test_api_has_no_secret_echo_and_no_provider_calls(settings, monkeypatch):
    import live_review.modules.asr.router as module

    app = FastAPI()
    install_errors(app)
    app.state.settings = settings
    actor = SimpleNamespace(workspace_id=uuid4())
    app.dependency_overrides[current_admin] = lambda: actor
    app.dependency_overrides[require_mutation] = lambda: actor
    app.include_router(router)
    monkeypatch.setattr(
        module, "create_provider", lambda *a: pytest.fail("unexpected provider call")
    )
    with TestClient(app) as client:
        path = "/api/v1/asr/tencent/settings"
        assert client.get(path).json()["revision"] == "unconfigured"
        response = client.put(
            path,
            json={
                "expected_revision": "unconfigured",
                "secret_id": "api-id",
                "secret_key": "api-key",
            },
        )
        assert response.status_code == 200 and response.json()["configured"]
        assert "api-key" not in response.text and "api-id" not in response.text
        assert client.put(path, json={"expected_revision": "unconfigured"}).status_code == 409
        saved = response.json()
        response = client.request("DELETE", path, json={"expected_revision": saved["revision"]})
        assert response.status_code == 200 and not response.json()["configured"]
        assert "private,no-store" in response.headers["cache-control"]


def test_tencent_health_does_not_contact_provider(settings, monkeypatch):
    import asyncio

    import live_review.modules.asr.router as module
    from live_review.modules.asr.schemas import SettingsOutput

    workspace = uuid4()
    save(Store(settings, workspace), secret_id="health-id", secret_key="health-key")
    monkeypatch.setattr(
        module,
        "settings_view",
        lambda *a: SettingsOutput(provider="tencent", privacy="cloud_allowed", revision=1),
    )

    class Provider:
        async def health(self):
            pytest.fail("Tencent health must not send network request")

    monkeypatch.setattr(module, "create_provider", lambda *a: Provider())
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings)))
    result = asyncio.run(module.health(request, SimpleNamespace(workspace_id=workspace), None))
    assert result["config_valid"] and result["network_checked"] is False


def test_snapshot_tampering_and_revision_stability(settings):
    workspace = uuid4()
    assert (
        registry_for(settings, workspace).snapshot() == registry_for(settings, workspace).snapshot()
    )
    data = payload(settings, workspace)
    data["workspace_asr_revision"] = "forged"
    with pytest.raises(ASRError, match="configuration_changed"):
        restore_gateway(data, settings, workspace)


def test_separate_namespaces_untouched(settings):
    from live_review.modules.llm.private_files import PrivateFiles

    workspace = uuid4()
    llm = PrivateFiles(settings, workspace)
    llm.write("fixture.secret", b"isolated-llm-secret")
    store = Store(settings, workspace)
    first = save(store, secret_id="separate-id", secret_key="separate-key")
    store.update(revision=first.revision)
    assert llm.read("fixture.secret", 1024) == b"isolated-llm-secret"


def test_corrupt_or_symlink_state_fails_closed(settings, tmp_path):
    store = Store(settings, uuid4())
    store.files.write("tencent.json", b"{}")
    with pytest.raises(ApiError):
        store.read()
    path = store.files.path / "tencent.json"
    path.unlink()
    outside = tmp_path / "outside"
    outside.write_text("must-not-read")
    path.symlink_to(outside)
    with pytest.raises(ApiError):
        store.read()


def test_new_local_job_survives_tencent_rotation_but_cannot_smuggle_cloud(settings):
    workspace = uuid4()
    data = payload(settings)
    data.update(
        workspace_asr_id=str(workspace),
        use_workspace_tencent=False,
        workspace_asr_revision=registry_for(settings).loaded.public.revision,
    )
    data["preferences"] = {"provider": "local", "allow_cloud_fallback": False}
    save(Store(settings, workspace), secret_id="rotated-id", secret_key="rotated-key")
    assert restore_gateway(data, settings, workspace)
    data["preferences"]["allow_cloud_fallback"] = True
    with pytest.raises(ASRError, match="configuration_changed"):
        restore_gateway(data, settings, workspace)
