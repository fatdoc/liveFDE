"""Memory-only URL relay: validates every HLS child/redirect and pins public DNS.

FFmpeg sees only loopback capability URLs; it never receives platform secrets or
untrusted playlists. No access logs, proxy environment, or arbitrary protocols.
"""

import http.client
import ipaddress
import json
import re
import secrets
import socket
import ssl
import subprocess
import sys
import threading
import time
from contextvars import ContextVar
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer
from urllib.parse import urljoin, urlsplit

from live_review.integrations.capture.contracts import CaptureError, StopCapture
from live_review.integrations.capture.hls import rewrite

# Per-call controls preserve destination(url, domains), including offline fixture adapters.
_resolution_controls = ContextVar("capture_resolution_controls", default=None)


def _resolver_command(host, port):
    # No URL, credentials, proxy settings or inherited application code reach this process.
    script = (
        "import json,socket,sys; "
        "rows=socket.getaddrinfo(sys.argv[1],int(sys.argv[2]),type=socket.SOCK_STREAM); "
        "print(json.dumps([row[4][0] for row in rows] if len(rows)<=256 else []))"
    )
    return [sys.executable, "-I", "-c", script, host, str(port)]


def resolve_addresses(host, port, *, deadline=None, tick=None, stopped=None):
    """Bound DNS in a killable subprocess, and reap it before returning or raising."""
    controls = _resolution_controls.get() or {}
    deadline = deadline if deadline is not None else controls.get("deadline")
    tick = tick if tick is not None else controls.get("tick")
    stopped = stopped if stopped is not None else controls.get("stopped")
    limit = min(deadline, time.monotonic() + 5) if deadline is not None else time.monotonic() + 5

    def check():
        if stopped is not None and stopped.is_set():
            raise StopCapture
        if tick is not None:
            tick()
        if time.monotonic() >= limit:
            raise CaptureError(
                "duration_limit"
                if deadline is not None and time.monotonic() >= deadline
                else "source_resolution_timeout"
            )

    process = None
    try:
        check()
        process = subprocess.Popen(
            _resolver_command(host, port),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        while True:
            check()
            try:
                output, _ = process.communicate(
                    timeout=max(0.001, min(0.1, limit - time.monotonic()))
                )
                break
            except subprocess.TimeoutExpired:
                continue
        check()
        if process.returncode or len(output) > 65536:
            raise CaptureError("source_resolution_failed")
        addresses = json.loads(output)
        if (
            not isinstance(addresses, list)
            or len(addresses) > 256
            or not all(isinstance(value, str) for value in addresses)
        ):
            raise CaptureError("source_resolution_failed")
        return addresses
    except (OSError, ValueError):
        raise CaptureError("source_resolution_failed") from None
    finally:
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        raise CaptureError("resolver_stop_unconfirmed") from None
            if process.stdout is not None:
                process.stdout.close()


def destination(url, domains):
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        if (
            parts.scheme not in {"http", "https"}
            or parts.username
            or parts.password
            or parts.fragment
            or parts.port not in {None, 80, 443}
            or any(ord(c) < 33 for c in url)
            or not any(host == d or host.endswith("." + d) for d in domains)
        ):
            raise CaptureError("unsafe_stream_url")
        port = parts.port or (443 if parts.scheme == "https" else 80)
        addresses = resolve_addresses(host, port)
        if not addresses or any(
            not ipaddress.ip_address(address).is_global for address in addresses
        ):
            raise CaptureError("unsafe_stream_url")
        return parts, addresses[0], port
    except (ValueError, OSError):
        raise CaptureError("unsafe_stream_url") from None


class LoopbackServer(ThreadingHTTPServer):
    def server_bind(self):
        # HTTPServer's default getfqdn() performs an unnecessary unbounded reverse lookup.
        TCPServer.server_bind(self)
        self.server_name, self.server_port = "127.0.0.1", self.server_address[1]


class Relay:
    def __init__(self, source, domains, *, deadline=None, tick=None, https_only=False):
        self.domains = domains
        self.deadline, self.tick, self.https_only = deadline, tick, https_only
        self.stopped = threading.Event()
        self.resolution_condition = threading.Condition()
        self.resolving = 0
        self.urls = {}
        self.reverse = {}
        self.lock = threading.Lock()
        self.error = None
        self.server = LoopbackServer(("127.0.0.1", 0), self.handler())
        self.server.daemon_threads = True
        try:
            self.url = self.register(source)
        except Exception:
            self.server.server_close()
            raise
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def destination(self, url):
        with self.resolution_condition:
            if self.stopped.is_set():
                raise StopCapture
            self.resolving += 1
        token = _resolution_controls.set(
            {"deadline": self.deadline, "tick": self.tick, "stopped": self.stopped}
        )
        try:
            # Enforce this before DNS, even when an offline test substitutes destination.
            if self.https_only and urlsplit(url).scheme != "https":
                raise CaptureError("https_required")
            return destination(url, self.domains)
        finally:
            _resolution_controls.reset(token)
            with self.resolution_condition:
                self.resolving -= 1
                self.resolution_condition.notify_all()

    def register(self, url, kind=None):
        # Validate before publishing; fetch revalidates and pins the actual connection.
        self.destination(url)
        with self.lock:
            identity = (url, kind)
            if identity in self.reverse:
                return self.reverse[identity]
            if len(self.urls) > 100000:
                raise CaptureError("playlist_limit")
            token = secrets.token_hex(24)
            suffix = urlsplit(url).path.rsplit(".", 1)[-1].lower()
            suffix = (
                "." + suffix
                if suffix
                in {"m3u8", "ts", "m4s", "mp4", "m4a", "aac", "mp3", "ac3", "ec3", "vtt", "flv"}
                else ".ts"
            )
            suffix = {"playlist": ".m3u8", "key": ".key", "map": ".mp4"}.get(kind, suffix)
            path = "/" + token + suffix
            self.urls[path] = url
            public = f"http://127.0.0.1:{self.server.server_port}{path}"
            self.reverse[identity] = public
            return public

    def fetch(self, url, range_header):
        for _ in range(5):
            parts, address, port = self.destination(url)
            conn = http.client.HTTPConnection(parts.hostname, port, timeout=10)
            sock = socket.create_connection((address, port), timeout=10)
            if parts.scheme == "https":
                sock = ssl.create_default_context().wrap_socket(
                    sock, server_hostname=parts.hostname
                )
            conn.sock = sock
            headers = {"User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity"}
            if range_header and re.fullmatch(r"bytes=\d+-\d*", range_header):
                headers["Range"] = range_header
            conn.request(
                "GET", parts.path + ("?" + parts.query if parts.query else ""), headers=headers
            )
            response = conn.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                target = response.getheader("Location")
                conn.close()
                if not target:
                    raise CaptureError("source_http_error")
                url = urljoin(url, target)
                continue
            return conn, response, url
        raise CaptureError("source_redirect_limit")

    def playlist(self, body, base):
        return rewrite(body, base, self.register)

    def handler(self):
        relay = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                conn = None
                try:
                    source = relay.urls.get(self.path)
                    if source is None:
                        self.send_error(404)
                        return
                    conn, response, actual = relay.fetch(source, self.headers.get("Range"))
                    if response.status not in {200, 206}:
                        relay.error = (
                            "address_expired"
                            if response.status in {401, 403, 410}
                            else "source_http_error"
                        )
                        self.send_error(502)
                        return
                    content_type = response.getheader("Content-Type", "")
                    first_bytes = response.read(4096)
                    playlist = (
                        first_bytes.lstrip(b"\xef\xbb\xbf\r\n ").startswith(b"#EXTM3U")
                        or "mpegurl" in content_type.lower()
                        or urlsplit(actual).path.endswith(".m3u8")
                    )
                    self.send_response(response.status)
                    if playlist:
                        body = relay.playlist(first_bytes + response.read(1048577), actual)
                        self.send_header("Content-Type", "application/vnd.apple.mpegurl")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                    else:
                        for name in ("Content-Type", "Content-Length", "Content-Range"):
                            if value := response.getheader(name):
                                self.send_header(name, value)
                        self.end_headers()
                        self.wfile.write(first_bytes)
                        while chunk := response.read(65536):
                            self.wfile.write(chunk)
                except StopCapture:
                    relay.error = relay.error or "capture_stopped"
                except CaptureError as exc:
                    relay.error = exc.code
                except (OSError, ValueError, http.client.HTTPException):
                    relay.error = relay.error or "stream_disconnected"
                finally:
                    if conn:
                        conn.close()

        return Handler

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stopped.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        with self.resolution_condition:
            if not self.resolution_condition.wait_for(lambda: self.resolving == 0, timeout=2):
                raise CaptureError("resolver_stop_unconfirmed")
