"""All parser and HTTP responses are synthetic; MockTransport never opens a socket."""

import asyncio
import io
import json
import sys
import types

import h11
import httpx
import pytest

from live_review.integrations.capture import douyin_bridge as bridge


@pytest.fixture
def parser(monkeypatch):
    state = {
        "requests": [],
        "status": 200,
        "body": {"room": {"status": 2}},
        "headers": {},
        "exception": None,
        "swallow": True,
        "stream": True,
    }
    spider, stream = types.ModuleType("src.spider"), types.ModuleType("src.stream")
    package = types.ModuleType("src")
    package.spider, package.stream = spider, stream
    for name, module in (("src", package), ("src.spider", spider), ("src.stream", stream)):
        monkeypatch.setitem(sys.modules, name, module)

    async def room(source, cookies=None):
        headers = {
            "cookie": "upstream-synthetic-default",
            "cOoKiE": "upstream-duplicate",
            "user-agent": "synthetic-client",
        }
        if cookies:
            headers["cookie"] = cookies
        try:
            text = await spider.async_req(
                "https://live.douyin.com/webcast/room/web/enter/", headers=headers
            )
            return json.loads(text).get("room", {})
        except Exception:
            if state["swallow"]:
                return {}
            raise

    async def select(*args):
        return (
            {"record_url": "https://synthetic.invalid/live.m3u8?private=fixture"}
            if state["stream"]
            else {}
        )

    spider.get_douyin_web_stream_data, stream.get_douyin_stream_url = room, select
    original = httpx.AsyncClient

    def transport(request):
        # Actual h11 header validation without making any network connection.
        h11.Request(method="GET", target="/", headers=request.headers.raw)
        state["requests"].append(request)
        if state["exception"]:
            raise state["exception"]
        body = state["body"]
        return httpx.Response(
            state["status"],
            headers=state["headers"],
            content=body if isinstance(body, str) else json.dumps(body),
        )

    def client(**kwargs):
        assert kwargs == {"verify": True, "trust_env": False, "timeout": 20}
        return original(transport=httpx.MockTransport(transport), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    return state


def resolve(cookie=""):
    return asyncio.run(bridge.resolve({"source": "https://live.douyin.com/123", "cookie": cookie}))


@pytest.mark.parametrize("cookie", ["", " ", "\t \n"])
def test_absent_cookie_removes_upstream_defaults_at_final_headers(parser, cookie):
    assert resolve(cookie)["live"] is True
    request = parser["requests"][0]
    assert "cookie" not in request.headers
    assert request.headers["user-agent"] == "synthetic-client"


def test_explicit_cookie_is_the_only_cookie(parser):
    assert resolve(" synthetic=private-value ")["live"] is True
    values = [value for key, value in parser["requests"][0].headers.raw if key.lower() == b"cookie"]
    assert values == [b"synthetic=private-value"]


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"status": 401}, "source_auth_required"),
        ({"status": 403}, "source_auth_required"),
        ({"status": 429}, "source_rate_limited"),
        ({"status": 503}, "source_http_error"),
        ({"status": 302}, "source_http_error"),
        ({"body": ""}, "source_empty_response"),
        (
            {
                "body": "<html>captcha private-fixture</html>",
                "headers": {"Content-Type": "text/html"},
            },
            "source_challenge_required",
        ),
        ({"body": "not-json-private-fixture"}, "source_schema_changed"),
        ({"body": []}, "source_schema_changed"),
        ({"body": {}}, "source_schema_changed"),
        ({"body": {"room": {"status": "2"}}}, "source_schema_changed"),
        ({"stream": False}, "source_schema_changed"),
        ({"exception": httpx.ReadTimeout("private-fixture")}, "source_timeout"),
        ({"exception": httpx.LocalProtocolError("private-fixture")}, "source_protocol_error"),
        ({"exception": httpx.ConnectError("private-fixture")}, "source_network_error"),
    ],
)
def test_error_classification_survives_upstream_swallowing(parser, changes, code):
    parser.update(changes)
    result = resolve()
    assert result == {"error": code}
    assert "private-fixture" not in json.dumps(result)


def test_explicit_offline_stays_distinct(parser):
    parser["body"] = {"room": {"status": 4}}
    assert resolve() == {"live": False}


def test_missing_upstream_dependency_has_safe_code(monkeypatch):
    monkeypatch.setitem(sys.modules, "src", types.ModuleType("src"))
    monkeypatch.delitem(sys.modules, "src.spider", raising=False)
    monkeypatch.delitem(sys.modules, "src.stream", raising=False)
    assert resolve() == {"error": "provider_dependencies_missing"}


def test_main_suppresses_upstream_output(parser, monkeypatch, capsys, tmp_path):
    original = sys.modules["src.spider"].get_douyin_web_stream_data

    async def noisy(*args, **kwargs):
        print("private-fixture-from-upstream")
        print("private-fixture-stderr", file=sys.stderr)
        return await original(*args, **kwargs)

    monkeypatch.setattr(sys.modules["src.spider"], "get_douyin_web_stream_data", noisy)
    monkeypatch.setitem(
        sys.modules,
        "loguru",
        types.SimpleNamespace(logger=types.SimpleNamespace(remove=lambda: None)),
    )
    monkeypatch.setitem(sys.modules, "src.logger", types.ModuleType("src.logger"))
    monkeypatch.setattr(
        sys,
        "stdin",
        types.SimpleNamespace(
            buffer=io.BytesIO(
                json.dumps(
                    {
                        "checkout": str(tmp_path),
                        "source": "https://live.douyin.com/123",
                        "cookie": "",
                    }
                ).encode()
            )
        ),
    )
    parser["status"] = 401
    bridge.main()
    output = capsys.readouterr()
    assert json.loads(output.out) == {"error": "source_auth_required"}
    assert output.err == "" and "private-fixture" not in output.out


@pytest.mark.parametrize(
    "selected,policy,expected",
    [
        (
            {
                "flv_url": "https://pull.example.com/live.flv",
                "record_url": "https://pull.example.com/live.m3u8",
            },
            {},
            "https://pull.example.com/live.flv",
        ),
        (
            {
                "flv_url": "http://pull.example.com/live.flv",
                "m3u8_url": "https://pull.example.com/live.m3u8",
            },
            {"https_only": True},
            "https://pull.example.com/live.m3u8",
        ),
        (
            {
                "flv_url": "https://pull.example.com/live.flv?codec=h265",
                "record_url": "https://pull.example.com/live.m3u8",
            },
            {},
            "https://pull.example.com/live.m3u8",
        ),
        (
            {
                "flv_url": "https://outside.invalid/live.flv",
                "record_url": "https://pull.example.com/live.m3u8",
            },
            {"stream_domains": ["example.com"]},
            "https://pull.example.com/live.m3u8",
        ),
    ],
)
def test_explicit_eligible_stream_selection(selected, policy, expected):
    assert bridge.select_stream(selected, policy) == expected


@pytest.mark.parametrize(
    "selected,policy,code",
    [
        (
            {
                "flv_url": "http://pull.example.com/live.flv",
                "record_url": "http://pull.example.com/live.m3u8",
            },
            {"https_only": True},
            "https_required",
        ),
        (
            {"record_url": "https://example.com.evil.invalid/live.m3u8?secret=fixture"},
            {"stream_domains": ["example.com"]},
            "domain_not_allowed",
        ),
        (
            {"record_url": "https://user:private@pull.example.com/live.m3u8"},
            {},
            "unsafe_stream_url",
        ),
        ({"record_url": "https://pull.example.com:invalid/live.m3u8"}, {}, "unsafe_stream_url"),
        ({"flv_url": "https://pull.example.com/live.flv?codec=h265"}, {}, "source_schema_changed"),
        ({}, {}, "source_schema_changed"),
    ],
)
def test_stream_selection_fails_without_rewriting_or_secret_errors(selected, policy, code):
    with pytest.raises(bridge.ParserFailure) as caught:
        bridge.select_stream(selected, policy)
    assert caught.value.code == code
    assert str(caught.value) == code
