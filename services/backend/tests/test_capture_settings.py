"""Workspace settings and worker snapshots, synthetic parser only; no platform requests."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from capture_fixture import capture_env as capture_env
from capture_fixture import materials as materials
from capture_fixture import start_run
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from live_review.core.errors import ApiError
from live_review.integrations.capture.contracts import CaptureError, Source
from live_review.integrations.capture.providers import DouyinProvider
from live_review.main import app
from live_review.modules.capture.credentials import CredentialStore
from live_review.modules.jobs.execution import Context, claim
from live_review.modules.jobs.models import Job, JobStage
from live_review.workers import capture_jobs

URL = "/api/v1/capture/settings/douyin"
SECRET = "synthetic_session=private_fixture"


@pytest.fixture
def settings_api(capture_env, monkeypatch):
    fixture, settings, _ = capture_env
    state = {"calls": [], "live": True, "error": None, "hook": None}
    monkeypatch.setattr(
        DouyinProvider,
        "health",
        lambda self: {
            "dependencies_ready": True,
            "real_platform_verified": False,
            "cookie_configured": bool(self._cookie),
            "requires_phone": False,
        },
    )

    def probe(self, source, tick):
        state["calls"].append((self._cookie, self.policy.probe_attempts, source))
        if state["hook"]:
            state["hook"]()
        if state["error"]:
            raise CaptureError(state["error"])
        return Source(state["live"], state.get("url", "https://cdn.douyincdn.com/private-stream"))

    monkeypatch.setattr(DouyinProvider, "probe", probe)
    return fixture, settings, state


def save(client, headers, revision="0", cookie=SECRET):
    response = client.put(
        URL, headers=headers, json={"cookie": cookie, "expected_revision": revision}
    )
    assert response.status_code == 200, response.text
    assert cookie not in response.text
    return response.json()


def check(client, headers, revision):
    return client.post(
        URL + "/check",
        headers=headers,
        json={"expected_revision": revision, "source_ref": "https://live.douyin.com/123"},
    )


def test_private_store_permissions_revision_and_workspace_isolation(tmp_path):
    settings = SimpleNamespace(storage_root=tmp_path / "storage")
    first, second = CredentialStore(settings, uuid4()), CredentialStore(settings, uuid4())
    saved = first.update("0", SECRET)
    assert SECRET not in repr(saved) and SECRET not in json.dumps(saved.public(False))
    assert second.read().cookie == ""
    assert not first.path.is_relative_to(settings.storage_root)
    assert first.path.stat().st_mode & 0o777 == 0o700
    assert (first.path / "douyin.json").stat().st_mode & 0o777 == 0o600
    with pytest.raises(ApiError) as error:
        first.update("0", "other=fixture")
    assert error.value.code == "revision_conflict"
    cleared = first.update(saved.revision, "")
    assert cleared.revision != saved.revision and cleared.status == "not_configured"
    assert SECRET not in (first.path / "douyin.json").read_text()


def test_private_store_rejects_symlink_and_exposed_permissions(tmp_path):
    settings = SimpleNamespace(storage_root=tmp_path / "storage")
    store = CredentialStore(settings, uuid4())
    target = tmp_path / "unrelated"
    target.write_text(SECRET)
    (store.path / "douyin.json").symlink_to(target)
    with pytest.raises(ApiError):
        store.read()
    (store.path / "douyin.json").unlink()
    store.update("0", SECRET)
    (store.path / "douyin.json").chmod(0o644)
    with pytest.raises(ApiError, match="平台设置暂不可用"):
        store.read()


def test_settings_save_update_clear_no_secret_or_env_fallback(settings_api, monkeypatch):
    fixture, settings, _ = settings_api
    client, headers, admin, _, _ = fixture
    monkeypatch.setenv("LIVE_CAPTURE_DOUYIN_COOKIE", "global=must_not_be_used")
    initial = client.get(URL).json()
    assert initial["revision"] == "0" and initial["status"] == "not_configured"
    assert not client.get("/api/v1/capture/health").json()["providers"]["douyin"][
        "cookie_configured"
    ]
    saved = save(client, headers)
    assert saved["status"] == "unverified" and saved["checked_at"] is None
    updated = save(client, headers, saved["revision"], "updated=fixture")
    response = client.request(
        "DELETE", URL, headers=headers, json={"expected_revision": updated["revision"]}
    )
    assert response.status_code == 200 and response.json()["status"] == "not_configured"
    assert not response.json()["configured"]
    assert CredentialStore(settings, admin.workspace_id).read().cookie == ""
    assert not client.get("/api/v1/capture/health").json()["providers"]["douyin"][
        "cookie_configured"
    ]


@pytest.mark.parametrize(
    "bad",
    ["", " \n", SECRET + "\r\nInjected: yes", "x" * 16385, {"cookie": SECRET}],
    ids=["empty", "whitespace", "injection", "oversized", "nonstring"],
)
def test_invalid_inputs_never_echo_cookie(settings_api, bad):
    fixture, _, _ = settings_api
    client, headers, _, _, _ = fixture
    response = client.put(URL, headers=headers, json={"cookie": bad, "expected_revision": "0"})
    assert (
        response.status_code == 422
        and SECRET not in response.text
        and "Injected" not in response.text
    )
    response = client.post(
        URL + "/check",
        headers=headers,
        json={"source_ref": "https://private.invalid/" + SECRET, "expected_revision": "0"},
    )
    assert response.status_code == 422 and SECRET not in response.text


def test_permissions_csrf_and_cross_workspace(settings_api):
    fixture, _, _ = settings_api
    client, headers, _, _, stranger = fixture
    for method, path, body in [
        ("PUT", URL, {"cookie": SECRET, "expected_revision": "0"}),
        ("DELETE", URL, {"expected_revision": "0"}),
        (
            "POST",
            URL + "/check",
            {"expected_revision": "0", "source_ref": "https://live.douyin.com/123"},
        ),
    ]:
        response = client.request(method, path, json=body)
        assert response.status_code == 403 and SECRET not in response.text
    save(client, headers)
    other = client.post(
        "/api/v1/auth/login",
        headers={"Origin": headers["Origin"]},
        json={"username": stranger.username, "password": "synthetic-material-password"},
    )
    assert other.status_code == 200
    assert not client.get(URL).json()["configured"]
    client.cookies.clear()
    assert client.get(URL).status_code == 401


@pytest.mark.parametrize("live", [True, False])
def test_single_parser_check_no_job_or_recording(settings_api, live):
    fixture, settings, state = settings_api
    client, headers, admin, _, _ = fixture
    revision = save(client, headers)["revision"]
    state["live"] = live
    with Session(app.state.engine) as db:
        before = db.scalar(select(func.count()).select_from(Job))
    response = check(client, headers, revision)
    assert response.status_code == 200
    value = response.json()
    assert value["status"] == "verified" and value["revision"] == revision
    assert value["checked_state"] == ("live" if live else "not_live")
    assert value["checked_at"] and value["last_error"] is None
    assert len(state["calls"]) == 1 and state["calls"][0][:2] == (SECRET, 1)
    assert "private-stream" not in response.text and SECRET not in response.text
    with Session(app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(Job)) == before
    assert CredentialStore(settings, admin.workspace_id).read().status == "verified"


@pytest.mark.parametrize(
    "error,status",
    [
        ("source_auth_required", "needs_update"),
        ("source_empty_response", "check_failed"),
        ("private-secret-error", "check_failed"),
    ],
)
def test_safe_failed_check_does_not_mislabel_empty_as_expired(settings_api, error, status):
    fixture, _, state = settings_api
    client, headers, _, _, _ = fixture
    revision = save(client, headers)["revision"]
    state["error"] = error
    response = check(client, headers, revision)
    assert response.status_code == 200 and response.json()["status"] == status
    expected = "source_parse_failed" if error.startswith("private") else error
    assert response.json()["last_error"] == expected
    assert "private-secret" not in response.text and len(state["calls"]) == 1


def test_check_nonreentrant_and_old_result_cannot_overwrite_update(settings_api):
    fixture, settings, state = settings_api
    client, headers, admin, _, _ = fixture
    revision = save(client, headers)["revision"]
    entered, release = threading.Event(), threading.Event()
    state["hook"] = lambda: (entered.set(), release.wait(5))
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(check, client, headers, revision)
        assert entered.wait(3)
        duplicate = check(client, headers, revision)
        assert duplicate.status_code == 409 and duplicate.json()["code"] == "platform_settings_busy"
        updated = save(client, headers, revision, "new=fixture")
        release.set()
        stale = pending.result(timeout=5)
    assert stale.status_code == 409 and stale.json()["code"] == "revision_conflict"
    assert len(state["calls"]) == 1
    value = client.get(URL).json()
    assert value["revision"] == updated["revision"] and value["status"] == "unverified"
    assert value["checked_at"] is None
    assert CredentialStore(settings, admin.workspace_id).read().cookie == "new=fixture"


def test_worker_reads_at_execution_and_keeps_immutable_snapshot(settings_api, monkeypatch):
    fixture, settings, _ = settings_api
    client, headers, admin, _, _ = fixture
    old = save(client, headers)
    run, _ = start_run(fixture)
    newer = save(client, headers, old["revision"], "queued=new")
    job_id = UUID(run["job_id"])
    token = claim(app.state.engine, job_id, 1, 30)
    with Session(app.state.engine) as db:
        stage = db.scalar(
            select(JobStage).where(JobStage.job_id == job_id, JobStage.name == "record")
        )
        stage_id = stage.id
        assert "cookie" not in json.dumps(db.get(Job, job_id).input_data)
    observed = []

    def acquire(self, source, tick):
        observed.append(self._cookie)
        CredentialStore(settings, admin.workspace_id).update(newer["revision"], "midrun=updated")
        observed.append(self._cookie)
        return Source(False)

    monkeypatch.setattr(DouyinProvider, "acquire", acquire)
    with pytest.raises(CaptureError, match="not_live"):
        capture_jobs.run_stage(
            Context(app.state.engine, job_id, token, stage_id, 30), settings, "capture.record"
        )
    assert observed == ["queued=new", "queued=new"]


def test_empty_workspace_probe_never_uses_global_env(settings_api, monkeypatch):
    fixture, _, state = settings_api
    client, headers, _, _, _ = fixture
    monkeypatch.setenv("LIVE_CAPTURE_DOUYIN_COOKIE", "global=forbidden")
    response = client.post(
        "/api/v1/capture/probe",
        headers=headers,
        json={"platform": "douyin", "source_ref": "https://live.douyin.com/123"},
    )
    assert response.status_code == 200 and state["calls"][0][0] == ""


@pytest.mark.parametrize(
    "url,error",
    [
        ("http://cdn.douyincdn.com/test", "https_required"),
        ("https://cdn.douyincdn.com.evil.invalid/test", "domain_not_allowed"),
        ("https://cdn.douyincdn.com:8443/test", "unsafe_stream_url"),
        ("https://user@cdn.douyincdn.com/test", "unsafe_stream_url"),
        ("https://@cdn.douyincdn.com/test", "unsafe_stream_url"),
        ("https://cdn.douyincdn.com/test#fragment", "unsafe_stream_url"),
        ("https://cdn.douyincdn.com/\ntest", "unsafe_stream_url"),
        (None, "unsafe_stream_url"),
    ],
)
def test_live_check_static_policy_no_network(settings_api, monkeypatch, url, error):
    import socket

    from live_review.integrations.capture.policy import CapturePolicy
    from live_review.modules.capture import platform_settings

    fixture, _, state = settings_api
    client, headers, _, _, _ = fixture
    revision = save(client, headers)["revision"]
    state["url"] = url
    monkeypatch.setattr(
        platform_settings, "load_policy", lambda _: CapturePolicy(enabled=True, https_only=True)
    )
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: pytest.fail("DNS forbidden"))
    response = check(client, headers, revision)
    assert response.status_code == 200
    assert response.json()["status"] == "check_failed"
    assert response.json()["last_error"] == error
    assert response.json()["checked_state"] is None
    assert len(state["calls"]) == 1
    state["live"] = False
    response = check(client, headers, revision)
    assert response.json()["status"] == "verified"
    assert response.json()["checked_state"] == "not_live"


def test_unconfigured_and_stale_check_do_not_probe(settings_api):
    fixture, _, state = settings_api
    client, headers, _, _, _ = fixture
    assert check(client, headers, "0").status_code == 422
    save(client, headers)
    assert check(client, headers, "0").status_code == 409
    assert state["calls"] == []


def test_private_store_without_storage_is_safe_503():
    with pytest.raises(ApiError) as error:
        CredentialStore(SimpleNamespace(storage_root=None), uuid4())
    assert error.value.status == 503
    assert error.value.code == "platform_storage_unavailable"
