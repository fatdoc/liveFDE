"""Isolated synthetic settings tests; no real service credentials or model traffic."""

from uuid import uuid4

import pytest
from test_llm_settings import api as text_api  # noqa: F401
from test_llm_settings import save as save_text

from live_review.core.errors import ApiError
from live_review.core.model_config.workspace_vision import effective_vision
from live_review.core.model_registry import ModelRegistry
from live_review.core.provider_config import ProviderConfigError
from live_review.modules.llm import vision_router
from live_review.modules.llm.store import Store as TextStore
from live_review.modules.llm.vision_schemas import Update
from live_review.modules.llm.vision_store import Store

URL = "/api/v1/llm/vision/settings"
SECRET = "synthetic-vision-secret"


@pytest.fixture
def api(text_api, monkeypatch):  # noqa: F811
    client, *rest = text_api
    client.app.include_router(vision_router.router)

    def network_forbidden(*args, **kwargs):
        raise AssertionError("settings must not perform network access")

    monkeypatch.setattr("socket.getaddrinfo", network_forbidden)
    monkeypatch.setattr("socket.create_connection", network_forbidden)
    yield client, *rest


def save(client, headers, revision="0", **changes):
    return client.put(
        URL,
        headers=headers,
        json={
            "expected_revision": revision,
            "enabled": True,
            "mode": "independent",
            "model": "vision-test",
            "base_url": "https://vision.example/v1",
            "api_key": SECRET,
            **changes,
        },
    )


def test_write_only_keep_switch_clear_and_cas(api):
    client, settings, headers, workspace, calls = api
    assert client.get(URL).json()["verification"] == "not_tested"
    value = save(client, headers).json()
    assert SECRET not in str(value) and value["configured"] and not value["analysis_enabled"]
    assert save(client, headers).status_code == 409
    store = Store(settings, workspace)
    assert store.secret(store._read()) == SECRET
    for mode in ("default", "independent"):
        value = client.put(
            URL,
            headers=headers,
            json={
                "expected_revision": value["revision"],
                "enabled": True,
                "mode": mode,
                "model": "next-vision",
                "base_url": "https://vision.example/v1",
            },
        ).json()
        assert value["independent_key_configured"]
        assert store.secret(store._read()) == SECRET
    value = client.request(
        "DELETE", URL, headers=headers, json={"expected_revision": value["revision"]}
    ).json()
    assert not value["enabled"] and not value["independent_key_configured"]
    assert not list(store.files.path.glob("*.secret")) and calls == []


def test_default_references_current_metadata_without_key_copy_or_tombstone_change(api):
    client, settings, headers, workspace, calls = api
    text = save_text(client, headers).json()
    text_store = TextStore(settings, workspace)
    request_id = uuid4()
    text_store.begin(text["revision"], request_id)
    before = text_store.files.read("state.json", 2097152)
    result = client.put(
        URL,
        headers=headers,
        json={
            "expected_revision": "0",
            "enabled": True,
            "mode": "default",
            "model": "vision",
        },
    ).json()
    assert result["configured"] and result["default_status"] == "checking"
    assert result["default_revision"] == text["revision"]
    assert text_store.files.read("state.json", 2097152) == before
    assert not list(Store(settings, workspace).files.path.glob("*.secret"))
    text = save_text(client, headers, text["revision"], base_url="https://new.example/v1").json()
    result = client.get(URL).json()
    assert result["effective_base_url"] == text["base_url"]
    assert result["default_revision"] == text["revision"]
    with pytest.raises(ApiError, match="该测试编号已使用"):
        text_store.begin(text["revision"], request_id)
    assert client.post(URL + "/check", headers=headers, json={}).status_code == 404
    assert calls == []


def test_auth_workspace_and_disabled_empty_model(api):
    client, _, headers, _, _ = api
    assert save(client, {}).status_code == 403
    assert save(client, headers).status_code == 200
    client.cookies.set("identity", "second")
    assert client.get(URL).json()["revision"] == "0"
    result = client.put(
        URL,
        headers=headers,
        json={
            "expected_revision": "0",
            "enabled": False,
            "mode": "default",
            "model": "",
        },
    )
    assert result.status_code == 200 and not result.json()["configured"]
    client.cookies.clear()
    assert client.get(URL).status_code == 401


@pytest.mark.parametrize(
    "changes",
    [
        {"api_key": ""},
        {"api_key": None},
        {"api_key": "x\nsecret"},
        {"mode": "default"},
        {"model": ""},
        {"base_url": "https://127.0.0.1/v1"},
        {"base_url": "http://vision.example/v1"},
        {"base_url": "https://user:secret@host/v1"},
    ],
)
def test_invalid_and_unsafe_configuration(api, changes):
    client, _, headers, _, calls = api
    response = save(client, headers, **changes)
    assert response.status_code == 422 and SECRET not in response.text and calls == []


def test_registry_declaration_and_http_metadata_only(api):
    client, settings, headers, workspace, _ = api
    value = save(client, headers).json()
    registry = ModelRegistry(effective_vision(settings, workspace))
    assert registry.get("vision.default").route.enabled is False
    with pytest.raises(ProviderConfigError, match="model_capability_not_executable"):
        registry.resolve("vision.default", allow_network=True)
    loaded = effective_vision(settings, workspace)
    assert not loaded.credential("LIVE_WORKSPACE_VISION_KEY")
    endpoint = "http://vision.example:8080/v1"
    settings.llm_debug_http_endpoints = [endpoint]
    result = save(client, headers, value["revision"], base_url=endpoint)
    assert result.status_code == 200 and result.json()["debug_http"]
    loaded = effective_vision(settings, workspace)
    assert all(m.name != "workspace_vision" for m in loaded.public.models)


def test_secret_atomicity_and_clear_does_not_touch_default(api, monkeypatch):
    client, settings, headers, workspace, _ = api
    save_text(client, headers)
    text_store = TextStore(settings, workspace)
    before = {p.name: p.read_bytes() for p in text_store.files.path.glob("*")}
    value = save(client, headers).json()
    store = Store(settings, workspace)
    original = store.files.write

    def fail_pointer(name, content):
        if name == "state.json":
            raise ApiError(503, "llm_storage_unavailable", "safe")
        original(name, content)

    monkeypatch.setattr(store.files, "write", fail_pointer)
    with pytest.raises(ApiError):
        store.update(
            Update(
                expected_revision=value["revision"],
                enabled=True,
                mode="independent",
                model="vision",
                base_url="https://other.example",
                api_key="synthetic-replacement",
            ),
            revision=value["revision"],
        )
    assert store._read().revision == value["revision"]
    assert store.secret(store._read()) == SECRET
    client.request("DELETE", URL, headers=headers, json={"expected_revision": value["revision"]})
    assert not list(store.files.path.glob("*.secret"))
    assert before == {p.name: p.read_bytes() for p in text_store.files.path.glob("*")}


def test_disabled_overlay_removes_its_stale_registry_declaration(api):
    client, settings, headers, workspace, _ = api
    value = save(client, headers).json()
    loaded = effective_vision(settings, workspace)
    assert any(m.name == "workspace_vision" for m in loaded.public.models)
    client.request("DELETE", URL, headers=headers, json={"expected_revision": value["revision"]})
    disabled = effective_vision(settings, workspace, loaded)
    assert all(m.name != "workspace_vision" for m in disabled.public.models)
    assert all(a.model != "workspace_vision" for a in disabled.public.aliases)
