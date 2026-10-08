"""Offline protocol/security regressions, not real CDN or recording acceptance."""

from types import SimpleNamespace

import pytest

from live_review.integrations.capture import recording, relay
from live_review.integrations.capture.contracts import CaptureError
from live_review.integrations.capture.policy import CapturePolicy
from live_review.integrations.capture.wechat_url import https_candidate, resolve_reference

HOST = "pull-l1.wxlivecdn.com"
BASE = f"https://{HOST}/live/main.m3u8?base=secret"


@pytest.fixture
def instance(monkeypatch):
    monkeypatch.setattr(relay, "resolve_addresses", lambda *_: ["1.1.1.1"])
    value = relay.Relay(BASE, ["wxlivecdn.com"], https_only=True, wechat_https_upgrade=True)
    yield value
    value.server.server_close()


@pytest.mark.parametrize("suffix", ["/x?", "/x?a=%2f&a=%2F&sig=a+b%20c", "?", "/x"])
@pytest.mark.parametrize("port", ["", ":80"])
def test_candidate_preserves_suffix(suffix, port):
    assert https_candidate(f"http://{HOST}{port}{suffix}", ["wxlivecdn.com"]) == (
        f"https://{HOST}{suffix}"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://wxlivecdn.com.evil.test/x",
        "http://evilwxlivecdn.com/x",
        "http://douyincdn.com/x",
        f"http://{HOST}:443/x",
        f"http://{HOST}:8080/x",
        f"http://@{HOST}/x",
        f"http://a:b@{HOST}/x",
        f"http://{HOST}/x#",
        f"http://{HOST}/x#fragment",
        f"http://{HOST}/x\x7f",
        f"http://{HOST}/x\n",
        f"http://{HOST}/x\t",
        f"http://{HOST}:bad/x",
        "http:///missing",
        f"http://{HOST}/x\\y",
    ],
)
def test_candidate_rejects_unsafe(url):
    with pytest.raises(CaptureError, match="unsafe_stream_url"):
        https_candidate(url, ["wxlivecdn.com", "douyincdn.com"])


def test_allowlist_and_https_unchanged():
    with pytest.raises(CaptureError):
        https_candidate(f"http://{HOST}/x", ["qq.com"])
    original = f"https://{HOST}:443/x?"
    assert https_candidate(original, ["wxlivecdn.com"]) == original
    assert https_candidate("http://wxlivecdn.com/x", ["wxlivecdn.com"]) == "https://wxlivecdn.com/x"


def test_default_off(monkeypatch):
    assert CapturePolicy().wechat_https_upgrade is False
    monkeypatch.setattr(relay, "resolve_addresses", lambda *_: pytest.fail("DNS called"))
    with pytest.raises(CaptureError, match="https_required"):
        relay.Relay(f"http://{HOST}/x", ["wxlivecdn.com"], https_only=True)


@pytest.mark.parametrize("platform,expected", [("wechat", True), ("douyin", False)])
def test_record_platform_gate(tmp_path, monkeypatch, platform, expected):
    class Intercept:
        def __init__(self, *args, **kwargs):
            assert kwargs["wechat_https_upgrade"] is expected
            assert kwargs["https_only"] is True
            raise CaptureError("test_intercept")

    monkeypatch.setattr(recording, "Relay", Intercept)
    monkeypatch.setattr(recording.shutil, "disk_usage", lambda _: SimpleNamespace(free=10**12))
    with pytest.raises(CaptureError, match="test_intercept"):
        recording.record(
            SimpleNamespace(url=BASE),
            tmp_path,
            CapturePolicy(wechat_https_upgrade=True, https_only=True),
            lambda: None,
            lambda _: None,
            platform,
            "run",
            "reference",
        )


@pytest.mark.parametrize(
    "reference,expected",
    [
        ("?", f"https://{HOST}/live/main.m3u8?"),
        ("child.ts?", f"https://{HOST}/live/child.ts?"),
        (f"http://{HOST}/x?", f"http://{HOST}/x?"),
        (f"//{HOST}/x?", f"https://{HOST}/x?"),
        ("child.ts?a=%2f&a=%2F", f"https://{HOST}/live/child.ts?a=%2f&a=%2F"),
    ],
)
def test_reference_query(reference, expected):
    assert resolve_reference(BASE, reference) == expected


def test_hls_all_resources(instance):
    master = f"""#EXTM3U
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="a",NAME="a",URI="http://{HOST}/audio.m3u8?"
#EXT-X-STREAM-INF:BANDWIDTH=100
http://{HOST}/variant.m3u8?sig=%2F&sig=%2f
""".encode()
    variant = f"""#EXTM3U
#EXT-X-KEY:METHOD=AES-128,URI="http://{HOST}/key?"
#EXT-X-MAP:URI="http://{HOST}/map.mp4?"
#EXTINF:1,
http://{HOST}/segment.ts?
#EXTINF:1,
relative.ts?sig=a+b
""".encode()
    for body in (master, variant):
        result = instance.playlist(body, BASE)
        assert b"wxlivecdn" not in result
        assert b"http://127.0.0.1:" in result
    assert set(instance.urls.values()) == {
        BASE,
        *(
            f"https://{HOST}/{x}"
            for x in [
                "audio.m3u8?",
                "variant.m3u8?sig=%2F&sig=%2f",
                "key?",
                "map.mp4?",
                "segment.ts?",
                "live/relative.ts?sig=a+b",
            ]
        ),
    }


def fake_transport(monkeypatch, statuses):
    calls, tls = [], []
    responses = iter(statuses)

    class Connection:
        def __init__(self, *args, **kwargs):
            self.sock = None

        def request(self, method, target, headers):
            calls.append((method, target, headers))

        def getresponse(self):
            status, location = next(responses)
            return SimpleNamespace(status=status, getheader=lambda _: location)

        def close(self):
            pass

    def wrap(sock, server_hostname):
        tls.append(server_hostname)
        return sock

    monkeypatch.setattr(relay.http.client, "HTTPConnection", Connection)
    monkeypatch.setattr(relay.socket, "create_connection", lambda *a, **k: object())
    monkeypatch.setattr(
        relay.ssl, "create_default_context", lambda: SimpleNamespace(wrap_socket=wrap)
    )
    return calls, tls


def test_fetch_tls_redirect_and_exact_request(instance, monkeypatch):
    calls, tls = fake_transport(monkeypatch, [(302, f"http://{HOST}:80/x?"), (200, None)])
    _, response, actual = instance.fetch(f"http://{HOST}/first?x=%2f&x=%2F", "bytes=1-2")
    assert response.status == 200 and actual == f"https://{HOST}/x?"
    assert [c[1] for c in calls] == ["/first?x=%2f&x=%2F", "/x?"]
    assert tls == [HOST, HOST]
    assert all("Cookie" not in c[2] and c[2]["Range"] == "bytes=1-2" for c in calls)


@pytest.mark.parametrize(
    "target",
    ["http://evil.test/x", "https://evil.test/x", f"http://{HOST}:8080/x", f"http://{HOST}/x\x7f"],
)
def test_redirect_rejected_before_second_connection(instance, monkeypatch, target):
    calls, _ = fake_transport(monkeypatch, [(302, target)])
    with pytest.raises(CaptureError):
        instance.fetch(BASE, None)
    assert len(calls) == 1


def test_each_hop_dns_private_rejected(instance, monkeypatch):
    calls, _ = fake_transport(monkeypatch, [(302, f"http://{HOST}/next")])
    resolutions = iter([["1.1.1.1"], ["127.0.0.1"]])
    monkeypatch.setattr(relay, "resolve_addresses", lambda *_: next(resolutions))
    with pytest.raises(CaptureError, match="unsafe_stream_url"):
        instance.fetch(BASE, None)
    assert len(calls) == 1


def test_redirect_loop_bounded(instance, monkeypatch):
    calls, _ = fake_transport(monkeypatch, [(302, f"http://{HOST}/loop")] * 5)
    with pytest.raises(CaptureError, match="source_redirect_limit"):
        instance.fetch(BASE, None)
    assert len(calls) == 5


def test_tls_failure_no_http_fallback(instance, monkeypatch):
    calls, _ = fake_transport(monkeypatch, [(200, None)])

    def fail(*args, **kwargs):
        raise relay.ssl.SSLCertVerificationError("offline fixture")

    monkeypatch.setattr(
        relay.ssl, "create_default_context", lambda: SimpleNamespace(wrap_socket=fail)
    )
    with pytest.raises(relay.ssl.SSLCertVerificationError):
        instance.fetch(BASE, None)
    assert calls == []


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.1.2.3", "::1"])
def test_hls_child_private_dns(instance, monkeypatch, ip):
    monkeypatch.setattr(relay, "resolve_addresses", lambda *_: [ip])
    with pytest.raises(CaptureError, match="unsafe_stream_url"):
        instance.playlist(f"#EXTM3U\nhttp://{HOST}/segment.ts\n".encode(), BASE)


def test_initial_source_normalized(monkeypatch):
    calls = []

    def dns(host, port):
        calls.append((host, port))
        return ["1.1.1.1"]

    monkeypatch.setattr(relay, "resolve_addresses", dns)
    value = relay.Relay(
        f"http://{HOST}:80/x?", ["wxlivecdn.com"], https_only=True, wechat_https_upgrade=True
    )
    try:
        assert list(value.urls.values()) == [f"https://{HOST}/x?"]
        assert calls == [(HOST, 443)]
    finally:
        value.server.server_close()
