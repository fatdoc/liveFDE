"""Real loopback TCP/HTTP, synthetic replies only; no external provider requests."""

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from test_llm_connection import configured  # noqa: F401

from live_review.integrations.llm import connection as impl


@pytest.mark.parametrize(
    "framing,expected",
    [
        ("length_close", None),
        ("http10", None),
        ("chunked_close", None),
        ("eof_close", None),
        ("truncated_length", "llm_response_invalid"),
        ("truncated_chunk", "llm_response_invalid"),
        ("truncated_trailer", "llm_response_invalid"),
        ("timeout", "llm_timeout"),
    ],
)
def test_real_local_http_framing(configured, monkeypatch, caplog, framing, expected):  # noqa: F811
    body = json.dumps({"choices": [{"message": {"content": "OK"}}]}).encode()
    response = b"HTTP/1.1 200 OK\r\nConnection: close\r\n"
    if framing in {"chunked_close", "truncated_chunk", "truncated_trailer"}:
        response += b"Transfer-Encoding: chunked\r\n\r\n"
        response += f"{len(body):x}\r\n".encode() + body + b"\r\n"
        if framing == "chunked_close":
            response += b"0\r\n\r\n"
        elif framing == "truncated_trailer":
            response += b"0\r\n"
    elif framing == "eof_close":
        response += b"\r\n" + body
    else:
        size = len(body) + (10 if framing == "truncated_length" else 0)
        response += f"Content-Length: {size}\r\n\r\n".encode() + body
        if framing == "http10":
            response = response.replace(b"HTTP/1.1", b"HTTP/1.0", 1)
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            calls.append(self.path)
            self.close_connection = True
            try:
                if framing == "timeout":
                    head, payload = response.split(b"\r\n\r\n", 1)
                    self.connection.sendall(head + b"\r\n\r\n")
                    time.sleep(1.2)
                    self.connection.sendall(payload)
                else:
                    self.connection.sendall(response)
            except OSError:
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01))
    thread.start()
    real_socket = socket.socket

    class LocalSocket(real_socket):
        def connect(self, address):
            assert address == ("8.8.8.8", 8080)
            # Only the test socket redirects the validated synthetic destination.
            return super().connect(server.server_address)

    monkeypatch.setattr(impl, "resolve_addresses", lambda *a, **kw: ["8.8.8.8"])
    monkeypatch.setattr(
        impl, "socket", SimpleNamespace(
            socket=LocalSocket, AF_INET=socket.AF_INET, AF_INET6=socket.AF_INET6,
            SHUT_RDWR=socket.SHUT_RDWR, SOCK_STREAM=socket.SOCK_STREAM,
        )
    )
    try:
        if expected:
            with pytest.raises(impl.CheckFailure) as failure:
                impl.check_connection(*configured)
            assert failure.value.code == expected and failure.value.unknown
        else:
            assert impl.check_connection(*configured) is None
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)
    assert calls == ["/v1/chat/completions"]
    assert "synthetic-secret" not in caplog.text
    assert "Authorization" not in caplog.text and "choices" not in caplog.text
