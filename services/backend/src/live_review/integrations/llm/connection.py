"""One bounded synthetic request, public pinned address, no proxy or retry machinery."""

import http.client
import ipaddress
import json
import logging
import socket
import ssl
import threading
import time
from urllib.parse import urlsplit

from live_review.core.model_config.llm_routes import endpoint
from live_review.integrations.capture.contracts import CaptureError
from live_review.integrations.capture.relay import resolve_addresses

logger = logging.getLogger(__name__)

MAX_BODY = 65536
SAFE_ERRORS = frozenset(
    {
        "llm_auth_failed",
        "llm_model_not_found",
        "llm_rate_limited",
        "llm_endpoint_rejected",
        "llm_http_not_allowed",
        "llm_dns_failed",
        "llm_timeout",
        "llm_response_invalid",
        "llm_response_too_large",
        "llm_upstream_failed",
        "llm_result_unknown",
        "llm_configuration_invalid",
        "llm_connection_failed",
        "llm_connection_lost",
        "llm_tls_failed",
        "llm_protocol_error",
        "llm_client_error",
    }
)


class CheckFailure(Exception):
    def __init__(self, code, *, unknown=False):
        self.code = code if code in SAFE_ERRORS else "llm_result_unknown"
        self.unknown = unknown
        super().__init__(self.code)


def logged_failure(code, *, phase, category, unknown=False):
    error = CheckFailure(code, unknown=unknown)
    # All fields are local enums; never log exception messages, target or payload.
    logger.warning(
        "llm_check_failed phase=%s category=%s code=%s unknown=%s",
        phase, category, error.code, unknown,
    )
    return error


class CompleteResponse(http.client.HTTPResponse):
    def _read_and_discard_trailer(self):
        # stdlib accepts EOF instead of the trailer terminator; require complete framing.
        for _ in range(100):
            line = self.fp.readline(65537)
            if not line or len(line) > 65536:
                raise http.client.IncompleteRead(b"")
            if line == b"\r\n":
                return
        raise http.client.IncompleteRead(b"")


def validate_target(settings, environment, base_url):
    try:
        if endpoint(base_url) != base_url:
            raise ValueError
        parts = urlsplit(base_url)
        if parts.scheme == "http" and (
            settings.environment != "development"
            or environment not in {"development", "test"}
            or base_url not in settings.llm_debug_http_endpoints
        ):
            raise CheckFailure("llm_http_not_allowed")
        # DNS names are checked after bounded resolution; literal IPs also fail here.
        try:
            address = ipaddress.ip_address(parts.hostname)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError
        return parts
    except (ValueError, TypeError):
        raise CheckFailure("llm_endpoint_rejected") from None


def parse_usage(raw):
    try:
        value = json.loads(raw)
        choices = value["choices"]
        content = choices[0]["message"]["content"]
        if (
            not isinstance(choices, list)
            or not choices
            or not isinstance(content, str)
            or not content.strip()
        ):
            raise ValueError
        usage = value.get("usage")
        if usage is None:
            return None
        if not isinstance(usage, dict):
            raise ValueError
        result = {
            k: usage[k]
            for k in ("prompt_tokens", "completion_tokens", "total_tokens")
            if k in usage
        }
        if any(type(v) is not int or not 0 <= v <= 1000000000 for v in result.values()):
            raise ValueError
        return result or None
    except (ValueError, TypeError, KeyError, IndexError, UnicodeError):
        raise CheckFailure("llm_response_invalid", unknown=True) from None


def check_connection(settings, loaded):
    from live_review.core.model_registry import ModelRegistry

    route = ModelRegistry(loaded).get("llm.default").route
    target = validate_target(settings, loaded.public.environment, route.base_url)
    key = loaded.credential(route.key_env)
    if not key:
        raise CheckFailure("llm_configuration_invalid")
    deadline = time.monotonic() + route.timeout_seconds

    def remaining():
        value = deadline - time.monotonic()
        if value <= 0:
            raise TimeoutError
        return value

    try:
        addresses = resolve_addresses(
            target.hostname,
            target.port or (443 if target.scheme == "https" else 80),
            deadline=deadline,
        )
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            raise CheckFailure("llm_endpoint_rejected")
    except CaptureError as error:
        raise CheckFailure(
            "llm_timeout"
            if error.code in {"source_resolution_timeout", "duration_limit"}
            else "llm_dns_failed"
        ) from None
    except ValueError:
        raise CheckFailure("llm_endpoint_rejected") from None

    resources, gate = [], threading.Lock()
    sent = False
    connection = None

    def expire():
        with gate:
            for resource in resources:
                try:
                    resource.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                resource.close()

    timer = threading.Timer(max(0, deadline - time.monotonic()), expire)
    timer.daemon = True
    timer.start()
    phase = "connect"
    try:
        address = ipaddress.ip_address(addresses[0])
        raw = socket.socket(
            socket.AF_INET6 if address.version == 6 else socket.AF_INET, socket.SOCK_STREAM
        )
        with gate:
            resources.append(raw)
        raw.settimeout(remaining())
        raw.connect((str(address), target.port or (443 if target.scheme == "https" else 80)))
        transport = raw
        if target.scheme == "https":
            phase = "tls"
            raw.settimeout(remaining())
            transport = ssl.create_default_context().wrap_socket(
                raw, server_hostname=target.hostname, do_handshake_on_connect=False
            )
            with gate:
                resources.append(transport)
            transport.settimeout(remaining())
            transport.do_handshake()
        connection = http.client.HTTPConnection(
            target.hostname, port=target.port or (443 if target.scheme == "https" else 80)
        )
        connection.response_class = CompleteResponse
        connection.sock = transport  # No second resolution; Host and TLS SNI remain original host.
        payload = json.dumps(
            {
                "model": route.model,
                "messages": [{"role": "user", "content": "Reply with OK."}],
                "max_tokens": 32,
                "stream": False,
            }
        ).encode()
        transport.settimeout(remaining())
        phase = "send"
        sent = True  # A partial write may already have reached the provider.
        connection.request(
            "POST",
            target.path.rstrip("/") + "/chat/completions",
            body=payload,
            headers={
                "Authorization": "Bearer " + key,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Connection": "close",
            },
        )
        phase = "headers"
        response = connection.getresponse()
        if response.status in {401, 403}:
            raise CheckFailure("llm_auth_failed")
        if response.status in {404, 429}:
            raise CheckFailure(
                "llm_model_not_found" if response.status == 404 else "llm_rate_limited"
            )
        if 300 <= response.status < 400:
            raise CheckFailure("llm_endpoint_rejected")
        if not 200 <= response.status < 300:
            raise CheckFailure("llm_upstream_failed", unknown=response.status >= 500)
        if response.getheader("Content-Encoding", "identity").lower() != "identity":
            raise CheckFailure("llm_response_invalid", unknown=True)
        length = response.getheader("Content-Length")
        if length is not None and (not length.isdigit() or int(length) > MAX_BODY):
            raise CheckFailure("llm_response_too_large", unknown=True)
        content = bytearray()
        phase = "body"
        # Python 3.11 closes a Connection: close transport after the last
        # Content-Length byte. Do not touch it again once the response is closed.
        while not response.isclosed():
            transport.settimeout(remaining())
            chunk = response.read1(min(8192, MAX_BODY + 1 - len(content)))
            if not chunk:
                break
            content.extend(chunk)
            if len(content) > MAX_BODY:
                raise CheckFailure("llm_response_too_large", unknown=True)
        # The deadline watchdog also produces EOF: timeout takes priority over framing.
        remaining()
        # read1() may return EOF with outstanding Content-Length instead of raising.
        if response.length not in {None, 0}:
            raise CheckFailure("llm_response_invalid", unknown=True)
        remaining()
        phase = "validate"
        return parse_usage(content)
    except CheckFailure as error:
        logged_failure(error.code, phase=phase, category="response", unknown=error.unknown)
        raise
    except http.client.IncompleteRead:
        raise logged_failure(
            "llm_timeout" if time.monotonic() >= deadline else "llm_response_invalid",
            phase=phase, category="incomplete_response", unknown=sent,
        ) from None
    except TimeoutError:
        raise logged_failure(
            "llm_timeout", phase=phase, category="timeout", unknown=sent
        ) from None
    except ssl.SSLError:
        raise logged_failure(
            "llm_tls_failed", phase=phase, category="tls", unknown=sent
        ) from None
    except http.client.HTTPException:
        raise logged_failure(
            "llm_timeout" if time.monotonic() >= deadline else "llm_protocol_error",
            phase=phase, category="protocol", unknown=sent,
        ) from None
    except OSError:
        raise logged_failure(
            "llm_timeout" if time.monotonic() >= deadline
            else "llm_connection_lost" if sent else "llm_connection_failed",
            phase=phase, category="transport", unknown=sent,
        ) from None
    except Exception:
        raise logged_failure(
            "llm_timeout" if time.monotonic() >= deadline else "llm_client_error",
            phase=phase, category="client", unknown=sent,
        ) from None
    finally:
        timer.cancel()
        if connection:
            connection.close()
        expire()
