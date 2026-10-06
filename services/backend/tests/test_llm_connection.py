"""Offline synthetic sockets and DNS outputs only; never contact a model endpoint."""

import json
import socket
import threading
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from live_review.core.model_config import load_model_config
from live_review.core.model_config.llm_routes import LLMDebugRoute
from live_review.core.model_config.workspace_llm import effective_llm
from live_review.core.provider_config import ProviderConfigError, ProviderRoute
from live_review.integrations.llm import connection as impl
from live_review.modules.llm.schemas import Public


@pytest.fixture
def configured(tmp_path):
    (tmp_path / "models").mkdir()
    settings = SimpleNamespace(
        environment="development",
        model_config_environment="test",
        llm_debug_http_endpoints=["http://models.example:8080/v1"],
        model_config_dir=tmp_path / "models",
        model_dotenv_path=None,
    )
    value = Public(
        revision=uuid4().hex,
        base_url="http://models.example:8080/v1",
        model="synthetic-model",
        timeout_seconds=1,
        configured=True,
    )
    return settings, effective_llm(settings, value, "synthetic-secret")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/v1",
        "https://169.254.169.254/v1",
        "https://user:pass@models.example/v1",
        "https://@models.example/v1",
        "https://models.example/v1?key=x",
        "https://models.example/v1#fragment",
        "https://models.example/%2e%2e/private",
        "https://models.example:444/v1",
        "https://models.example/a/../v1",
        "https://models.example/\nv1",
        "file:///etc/passwd",
        "https://models.example/v1?",
        "https://models.example/v1#",
    ],
)
def test_unsafe_endpoint_rejected_without_dns(configured, url, monkeypatch):
    settings, _ = configured
    monkeypatch.setattr(
        impl, "resolve_addresses", lambda *args, **kwargs: pytest.fail("DNS forbidden")
    )
    with pytest.raises(impl.CheckFailure):
        impl.validate_target(settings, "test", url)


@pytest.mark.parametrize(
    "runtime,environment,allowlist",
    [
        ("production", "test", ["http://models.example:8080/v1"]),
        ("development", "production", ["http://models.example:8080/v1"]),
        ("development", "test", []),
        ("development", "test", ["http://models.example:8080"]),
        ("development", "test", ["http://models.example:8080/v1/"]),
    ],
)
def test_plaintext_exact_server_permission(configured, runtime, environment, allowlist):
    settings, _ = configured
    settings.environment, settings.llm_debug_http_endpoints = runtime, allowlist
    with pytest.raises(impl.CheckFailure, match="llm_http_not_allowed"):
        impl.validate_target(settings, environment, "http://models.example:8080/v1")


def test_ordinary_route_stays_https_and_debug_forbidden_in_production(configured):
    settings, _ = configured
    with pytest.raises(ValueError):
        ProviderRoute(
            protocol="openai_compatible",
            model="m",
            base_url="http://models.example/v1",
            provider="fixture",
            key_env="KEY",
            max_requests=1,
            max_cost_usd=1,
        )
    settings.environment, settings.model_config_environment = "production", "production"
    with pytest.raises(ProviderConfigError):
        effective_llm(
            settings,
            Public(revision=uuid4().hex, base_url="http://models.example/v1", model="m"),
            "secret",
        )
    (settings.model_config_dir / "models.yaml").write_text(
        "models:\n  debug:\n    capability: llm\n    route:\n      protocol: llm_debug\n"
        "      base_url: http://models.example/v1\n      model: m\n"
    )
    with pytest.raises(ProviderConfigError):
        load_model_config(settings.model_config_dir, environment="production")
    assert LLMDebugRoute(base_url="http://models.example/v1", model="m").enabled is False


@pytest.mark.parametrize(
    "addresses", [["8.8.8.8", "127.0.0.1"], ["::1"], ["169.254.169.254"], ["100.64.0.1"], []]
)
def test_all_dns_results_must_be_public(configured, monkeypatch, addresses):
    settings, loaded = configured
    monkeypatch.setattr(impl, "resolve_addresses", lambda *args, **kwargs: addresses)
    monkeypatch.setattr(impl.socket, "socket", lambda *args: pytest.fail("connect forbidden"))
    with pytest.raises(impl.CheckFailure, match="llm_endpoint_rejected"):
        impl.check_connection(settings, loaded)


def wire(monkeypatch, response, *, delay_headers=0, delay_body=0):
    """A socketpair gives http.client real framing without any network connection."""
    local, remote = socket.socketpair()
    requests, pins = [], []

    class Pinned:
        def __getattr__(self, name):
            return getattr(local, name)

        def connect(self, address):
            pins.append(address)

    monkeypatch.setattr(impl.socket, "socket", lambda *args: Pinned())
    monkeypatch.setattr(impl, "resolve_addresses", lambda *args, **kwargs: ["8.8.8.8"])

    def serve():
        try:
            remote.settimeout(3)
            data = bytearray()
            while b"\r\n\r\n" not in data:
                data.extend(remote.recv(4096))
            head, body = data.split(b"\r\n\r\n", 1)
            size = int(
                next(
                    line.split(b":", 1)[1]
                    for line in head.split(b"\r\n")
                    if line.lower().startswith(b"content-length:")
                )
            )
            while len(body) < size:
                body.extend(remote.recv(4096))
            requests.append((bytes(head), json.loads(body)))
            time.sleep(delay_headers)
            if delay_body:
                headers, payload = response.split(b"\r\n\r\n", 1)
                remote.sendall(headers + b"\r\n\r\n")
                for char in payload:
                    remote.sendall(bytes([char]))
                    time.sleep(delay_body)
            else:
                remote.sendall(response)
        except (OSError, StopIteration):
            pass
        finally:
            remote.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return requests, pins, thread


def success():
    body = json.dumps(
        {"choices": [{"message": {"content": "OK"}}], "usage": {"total_tokens": 5}}
    ).encode()
    return b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body


def test_one_pinned_post_preserves_path_ignores_proxy_and_discards_text(configured, monkeypatch):
    settings, loaded = configured
    monkeypatch.setenv("HTTPS_PROXY", "http://private.invalid:8000")
    monkeypatch.setenv("HTTP_PROXY", "http://private.invalid:8000")
    requests, pins, thread = wire(monkeypatch, success())
    assert impl.check_connection(settings, loaded) == {"total_tokens": 5}
    thread.join(2)
    assert pins == [("8.8.8.8", 8080)] and len(requests) == 1
    head, body = requests[0]
    assert head.startswith(b"POST /v1/chat/completions HTTP/1.1")
    assert b"Host: models.example:8080" in head
    assert body == {
        "model": "synthetic-model",
        "messages": [{"role": "user", "content": "Reply with OK."}],
        "max_tokens": 32,
        "stream": False,
    }


@pytest.mark.parametrize(
    "status,expected,unknown",
    [
        (301, "llm_endpoint_rejected", False),
        (401, "llm_auth_failed", False),
        (404, "llm_model_not_found", False),
        (429, "llm_rate_limited", False),
        (500, "llm_upstream_failed", True),
    ],
)
def test_status_errors_no_redirect_or_retries(configured, monkeypatch, status, expected, unknown):
    requests, _, thread = wire(
        monkeypatch,
        (
            f"HTTP/1.1 {status} Synthetic\r\n"
            "Location: http://127.0.0.1/private\r\nContent-Length: 0\r\n\r\n"
        ).encode(),
    )
    with pytest.raises(impl.CheckFailure) as error:
        impl.check_connection(*configured)
    thread.join(2)
    assert error.value.code == expected and error.value.unknown is unknown
    assert len(requests) == 1


@pytest.mark.parametrize(
    "body",
    [
        b"{}",
        b'{"choices":[]}',
        b'{"choices":[{"message":{"content":""}}]}',
        b'{"choices":[{"message":{"content":"OK"}}],"usage":{"total_tokens":true}}',
    ],
)
def test_invalid_success_response_is_unknown(body):
    with pytest.raises(impl.CheckFailure) as error:
        impl.parse_usage(body)
    assert error.value.code == "llm_response_invalid" and error.value.unknown


@pytest.mark.parametrize("declared", [True, False])
def test_body_bound(configured, monkeypatch, declared):
    body = b"x" * (impl.MAX_BODY + 1)
    header = (
        b"Content-Length: " + str(len(body)).encode() + b"\r\n"
        if declared
        else b"Connection: close\r\n"
    )
    requests, _, thread = wire(monkeypatch, b"HTTP/1.1 200 OK\r\n" + header + b"\r\n" + body)
    with pytest.raises(impl.CheckFailure, match="llm_response_too_large"):
        impl.check_connection(*configured)
    thread.join(2)
    assert len(requests) == 1


@pytest.mark.parametrize("headers,body", [(1.5, 0), (0, 0.1)])
def test_total_deadline_includes_slow_headers_and_drip_body(configured, monkeypatch, headers, body):
    _, _, thread = wire(monkeypatch, success(), delay_headers=headers, delay_body=body)
    started = time.monotonic()
    with pytest.raises(impl.CheckFailure) as error:
        impl.check_connection(*configured)
    assert time.monotonic() - started < 1.4
    assert error.value.code == "llm_timeout" and error.value.unknown
    thread.join(2)


def test_https_pins_ip_but_uses_default_certificate_verification_and_original_sni(
    configured, monkeypatch
):
    import ssl

    settings, loaded = configured
    value = Public(
        revision=uuid4().hex,
        base_url="https://models.example/v1",
        model="synthetic-model",
        timeout_seconds=1,
        configured=True,
    )
    loaded = effective_llm(settings, value, "synthetic-secret")
    real_context = ssl.create_default_context()
    assert real_context.verify_mode == ssl.CERT_REQUIRED and real_context.check_hostname
    requests, pins, thread = wire(monkeypatch, success())
    seen = []

    class TLS:
        def wrap_socket(self, raw, *, server_hostname, do_handshake_on_connect):
            seen.append(server_hostname)
            assert do_handshake_on_connect is False
            raw.do_handshake = lambda: seen.append("handshake")
            return raw

    monkeypatch.setattr(impl.ssl, "create_default_context", lambda: TLS())
    assert impl.check_connection(settings, loaded) == {"total_tokens": 5}
    thread.join(2)
    assert seen == ["models.example", "handshake"]
    assert pins == [("8.8.8.8", 443)] and len(requests) == 1


def test_dns_receives_total_deadline_and_failure_does_not_send(configured, monkeypatch):
    from live_review.integrations.capture.contracts import CaptureError

    def resolve(host, port, *, deadline):
        assert host == "models.example" and port == 8080
        assert 0 < deadline - time.monotonic() <= 1
        raise CaptureError("source_resolution_timeout")

    monkeypatch.setattr(impl, "resolve_addresses", resolve)
    monkeypatch.setattr(impl.socket, "socket", lambda *args: pytest.fail("TCP forbidden"))
    with pytest.raises(impl.CheckFailure) as error:
        impl.check_connection(*configured)
    assert error.value.code == "llm_timeout" and not error.value.unknown
