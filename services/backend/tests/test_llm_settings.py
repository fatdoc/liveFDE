"""API and durable storage fixtures with real auth mutation guards; no model calls or DB."""

import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from live_review.core.auth import current_admin
from live_review.core.errors import ApiError, install_errors
from live_review.core.model_config import load_model_config
from live_review.core.model_config.workspace_llm import effective_llm
from live_review.core.model_registry import ModelRegistry
from live_review.core.provider_config import ProviderConfigError
from live_review.integrations.llm.connection import CheckFailure
from live_review.modules.llm import router as implementation
from live_review.modules.llm.schemas import Update
from live_review.modules.llm.store import Store

URL = "/api/v1/llm/settings"
SECRET = "synthetic-test-secret"


@pytest.fixture
def api(tmp_path, monkeypatch):
    config = tmp_path / "models"
    config.mkdir()
    settings = SimpleNamespace(
        storage_root=tmp_path / "storage",
        model_config_dir=config,
        model_dotenv_path=None,
        model_config_environment="test",
        environment="development",
        llm_debug_http_endpoints=[],
        trusted_origins=["http://testserver"],
    )
    app = FastAPI()
    app.state.settings = settings
    install_errors(app)
    app.include_router(implementation.router)
    workspace = uuid4()

    def admin(request: Request):
        cookie = request.cookies.get("identity")
        if cookie not in {"first", "second"}:
            raise ApiError(401, "authentication_required", "Authentication required")
        request.state.auth_session = SimpleNamespace(csrf_token="fixture-csrf")
        return SimpleNamespace(workspace_id=workspace if cookie == "first" else other)

    other = uuid4()
    app.dependency_overrides[current_admin] = admin
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set("identity", "first")
    headers = {"Origin": "http://testserver", "X-CSRF-Token": "fixture-csrf"}
    calls = []

    def check(settings, loaded):
        calls.append(loaded)
        return {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4}

    monkeypatch.setattr(implementation, "check_connection", check)
    yield client, settings, headers, workspace, calls
    client.close()


def save(client, headers, revision="0", **updates):
    return client.put(
        URL,
        headers=headers,
        json={
            "expected_revision": revision,
            "base_url": "https://models.example/v1",
            "model": "synthetic-model",
            "timeout_seconds": 2,
            "api_key": SECRET,
            **updates,
        },
    )


def check(client, headers, revision, request_id=None):
    return client.post(
        URL + "/check",
        headers=headers,
        json={"expected_revision": revision, "request_id": str(request_id or uuid4())},
    )


def test_save_refresh_keep_replace_clear_private_permissions_and_zero_network(api):
    client, settings, headers, workspace, calls = api
    initial = client.get(URL).json()
    assert initial["base_url"] == "" and initial["timeout_seconds"] == 60
    assert initial["analysis_enabled"] is False
    saved = save(client, headers)
    assert saved.status_code == 200 and SECRET not in saved.text
    value = saved.json()
    assert value["status"] == "unverified" and value["configured"]
    payload = {
        "expected_revision": value["revision"],
        "base_url": value["base_url"],
        "model": "new-model",
        "timeout_seconds": 3,
    }
    kept = client.put(URL, headers=headers, json=payload).json()
    store = Store(settings, workspace)
    assert store.secret(store.read()) == SECRET
    assert store.files.path.stat().st_mode & 0o777 == 0o700
    assert not store.files.path.is_relative_to(settings.storage_root)
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in store.files.path.iterdir())
    assert SECRET not in (store.files.path / "state.json").read_text()
    assert calls == []
    refreshed = client.get(URL).json()
    assert refreshed == kept and refreshed["model"] == "new-model"
    cleared = client.request(
        "DELETE", URL, headers=headers, json={"expected_revision": kept["revision"]}
    ).json()
    assert not cleared["configured"] and cleared["model"] == "new-model"
    assert store.secret(store.read()) == ""
    assert not list(store.files.path.glob("*.secret"))


@pytest.mark.parametrize(
    "key",
    ["", "  ", "private\nHeader:value", "x" * 4097, None, {"private": "secret"}],
    ids=["empty", "whitespace", "newline", "large", "null", "object"],
)
def test_invalid_key_safe_validation(api, key):
    client, _, headers, _, calls = api
    response = save(client, headers, api_key=key)
    assert response.status_code == 422
    assert "Header" not in response.text and "private" not in response.text and calls == []


def test_auth_csrf_workspace_and_revision(api):
    client, _, headers, _, calls = api
    assert save(client, {}).status_code == 403
    assert (
        save(client, {"Origin": "http://evil", "X-CSRF-Token": "fixture-csrf"}).status_code == 403
    )
    saved = save(client, headers).json()
    assert save(client, headers).status_code == 409
    client.cookies.set("identity", "second")
    assert client.get(URL).json()["configured"] is False
    assert check(client, headers, saved["revision"]).status_code == 409
    client.cookies.clear()
    assert client.get(URL).status_code == 401 and calls == []


def test_check_cache_no_replay_across_revision_and_clear(api):
    client, _, headers, _, calls = api
    revision = save(client, headers).json()["revision"]
    rid = uuid4()
    first = check(client, headers, revision, rid)
    assert first.status_code == 200 and first.json()["status"] == "verified"
    assert first.json()["usage"]["total_tokens"] == 4
    assert check(client, headers, revision, rid).json() == first.json()
    assert len(calls) == 1
    new = save(client, headers, revision).json()
    assert check(client, headers, new["revision"], rid).status_code == 409
    cleared = client.request(
        "DELETE", URL, headers=headers, json={"expected_revision": new["revision"]}
    ).json()
    assert check(client, headers, cleared["revision"], rid).status_code == 409
    assert len(calls) == 1


def test_unknown_replay_and_restart_marker_remain_unknown(api, monkeypatch):
    client, settings, headers, workspace, calls = api
    revision = save(client, headers).json()["revision"]
    store = Store(settings, workspace)
    rid = uuid4()
    store.begin(revision, rid)  # Simulated process exit after durable marker, before response.
    assert client.get(URL).json()["status"] == "unknown"
    assert check(client, headers, revision, rid).json()["status"] == "unknown"
    assert calls == []
    assert check(client, headers, revision).status_code == 409
    revision = save(client, headers, revision).json()["revision"]

    def fail(*args):
        calls.append(True)
        raise CheckFailure("llm_timeout", unknown=True)

    monkeypatch.setattr(implementation, "check_connection", fail)
    rid = uuid4()
    assert check(client, headers, revision, rid).json()["status"] == "unknown"
    assert check(client, headers, revision, rid).json()["status"] == "unknown"
    assert check(client, headers, revision).status_code == 409
    assert len(calls) == 1


def test_mutation_during_call_cannot_apply_stale_result(api, monkeypatch):
    client, _, headers, _, calls = api
    revision = save(client, headers).json()["revision"]
    entered, release = threading.Event(), threading.Event()

    def blocking(*args):
        calls.append(True)
        entered.set()
        assert release.wait(5)
        return None

    monkeypatch.setattr(implementation, "check_connection", blocking)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(check, client, headers, revision)
        assert entered.wait(3)
        assert client.get(URL).json()["status"] == "checking"
        assert check(client, headers, revision).status_code == 409
        new = save(client, headers, revision).json()
        release.set()
        assert future.result(3).status_code == 409
    current = client.get(URL).json()
    assert current["revision"] == new["revision"] and current["status"] == "unverified"
    assert current["checked_at"] is None and len(calls) == 1


def test_effective_registry_preserves_asr_and_does_not_execute_analysis(api):
    client, settings, headers, workspace, _ = api
    value = save(client, headers).json()
    store = Store(settings, workspace)
    before = load_model_config(settings.model_config_dir, environment="test")
    loaded = effective_llm(settings, store.read(), store.secret(store.read()))
    before_registry, registry = ModelRegistry(before), ModelRegistry(loaded)
    assert registry.get("asr.default") == before_registry.get("asr.default")
    assert registry.get("llm.default").route.base_url == value["base_url"]
    assert SECRET not in repr(loaded) and SECRET not in loaded.model_dump_json()
    with pytest.raises(ProviderConfigError, match="model_capability_not_executable"):
        registry.resolve("llm.default", allow_network=True)


def test_secret_revision_atomicity_on_failed_pointer_update(api, monkeypatch):
    client, settings, headers, workspace, _ = api
    value = save(client, headers).json()
    store = Store(settings, workspace)
    original = store.files.write

    def failing(name, content):
        if name == "state.json":
            raise ApiError(503, "llm_storage_unavailable", "safe")
        original(name, content)

    monkeypatch.setattr(store.files, "write", failing)
    with pytest.raises(ApiError):
        store.update(
            Update(
                expected_revision=value["revision"],
                base_url="https://new.example/v1",
                model="new-model",
                timeout_seconds=3,
                api_key="replacement",
            ),
            revision=value["revision"],
        )
    assert store._read().value.revision == value["revision"]
    assert store.secret(store._read().value) == SECRET


def test_debug_permission_recomputed_and_unapproved_save_is_zero_network(api):
    client, settings, headers, _, calls = api
    endpoint = "http://models.example:8080/v1"
    denied = save(client, headers, base_url=endpoint)
    assert denied.status_code == 422 and denied.json()["code"] == "llm_http_not_allowed"
    settings.llm_debug_http_endpoints = [endpoint]
    saved = save(client, headers, base_url=endpoint).json()
    assert saved["debug_http"] is True
    settings.llm_debug_http_endpoints = []
    assert client.get(URL).json()["debug_http"] is False
    settings.llm_debug_http_endpoints = [endpoint]
    settings.environment = "production"
    assert client.get(URL).json()["debug_http"] is False
    cleared = client.request(
        "DELETE", URL, headers=headers, json={"expected_revision": saved["revision"]}
    ).json()
    assert cleared["debug_http"] is False and not cleared["configured"]
    assert calls == []


def test_clear_removes_orphan_secret_from_failed_prior_write(api):
    client, settings, headers, workspace, _ = api
    saved = save(client, headers).json()
    store = Store(settings, workspace)
    store.files.write(uuid4().hex + ".secret", b"synthetic-orphan")
    assert len(list(store.files.path.glob("*.secret"))) == 2
    assert (
        client.request(
            "DELETE", URL, headers=headers, json={"expected_revision": saved["revision"]}
        ).status_code
        == 200
    )
    assert list(store.files.path.glob("*.secret")) == []


def test_private_files_reject_symlinks_permissions_and_missing_storage(tmp_path):
    settings = SimpleNamespace(storage_root=tmp_path / "storage")
    store = Store(settings, uuid4())
    target = tmp_path / "unrelated"
    target.write_text("synthetic-private")
    state = store.files.path / "state.json"
    state.symlink_to(target)
    with pytest.raises(ApiError) as error:
        store.read()
    assert error.value.code == "llm_storage_unavailable"
    state.unlink()
    store.files.write("state.json", b"{}")
    state.chmod(0o644)
    with pytest.raises(ApiError):
        store.read()
    with pytest.raises(ApiError):
        Store(SimpleNamespace(storage_root=None), uuid4())


def test_no_env_key_fallback_and_unknown_error_no_secret_or_log(api, monkeypatch, capsys):
    client, _, headers, _, calls = api
    monkeypatch.setenv("LIVE_WORKSPACE_LLM_KEY", "synthetic-global-forbidden")
    assert check(client, headers, "0").status_code == 422
    revision = save(client, headers).json()["revision"]

    def fail(*args):
        raise RuntimeError("private raw body: " + SECRET)

    monkeypatch.setattr(implementation, "check_connection", fail)
    result = check(client, headers, revision)
    assert (
        result.json()["status"] == "unknown" and result.json()["last_error"] == "llm_result_unknown"
    )
    assert SECRET not in result.text and "private raw body" not in result.text
    assert not capsys.readouterr().out
    assert calls == []
