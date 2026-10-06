"""Memory-only URL relay: validates every HLS child/redirect and pins public DNS.

FFmpeg sees only loopback capability URLs; it never receives platform secrets or
untrusted playlists. No access logs, proxy environment, or arbitrary protocols.
"""

import http.client
import ipaddress
import re
import secrets
import socket
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urljoin, urlsplit

from live_review.integrations.capture.contracts import CaptureError


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
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise CaptureError("unsafe_stream_url")
        return parts, addresses[0][4][0], port
    except (ValueError, OSError):
        raise CaptureError("unsafe_stream_url") from None


class Relay:
    def __init__(self, source, domains):
        self.domains = domains
        self.urls = {}
        self.reverse = {}
        self.lock = threading.Lock()
        self.error = None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.handler())
        self.server.daemon_threads = True
        try:
            self.url = self.register(source)
        except Exception:
            self.server.server_close()
            raise
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def register(self, url):
        # Validate before publishing; fetch revalidates and pins the actual connection.
        destination(url, self.domains)
        with self.lock:
            if url in self.reverse:
                return self.reverse[url]
            if len(self.urls) > 100000:
                raise CaptureError("playlist_limit")
            token = secrets.token_hex(24)
            suffix = ".m3u8" if ".m3u8" in urlsplit(url).path else ".media"
            path = "/" + token + suffix
            self.urls[path] = url
            public = f"http://127.0.0.1:{self.server.server_port}{path}"
            self.reverse[url] = public
            return public

    def fetch(self, url, range_header):
        for _ in range(5):
            parts, address, port = destination(url, self.domains)
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
        if len(body) > 1048576:
            raise CaptureError("playlist_limit")
        lines = []
        for line in body.decode("utf-8-sig").splitlines():
            if line and not line.startswith("#"):
                line = self.register(urljoin(base, line.strip()))
            elif line.startswith("#"):
                line = re.sub(
                    r'URI="([^"\r\n]+)"',
                    lambda m: 'URI="' + self.register(urljoin(base, m[1])) + '"',
                    line,
                )
            lines.append(line)
        return ("\n".join(lines) + "\n").encode()

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
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
