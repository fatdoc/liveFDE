"""Pinned DLR parser bridge; private JSON pipes, no upstream scheduler or logs."""

import asyncio
import contextlib
import io
import json
import pathlib
import sys
import types
from urllib.parse import urlsplit


class ParserFailure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


async def resolve(data):
    try:
        import httpx
        from src import spider, stream
    except ImportError:
        return {"error": "provider_dependencies_missing"}

    cookie = data.get("cookie", "")
    cookie = cookie.strip() if isinstance(cookie, str) else ""
    last_error, received_response = None, False

    async def verified_request(url, proxy_addr=None, headers=None, **kwargs):
        nonlocal last_error, received_response
        try:
            parts = urlsplit(url)
            if (
                parts.scheme != "https"
                or parts.hostname != "live.douyin.com"
                or parts.port not in {None, 443}
                or parts.username
                or parts.password
            ):
                raise ParserFailure("source_protocol_error")
            # Upstream has a built-in Cookie when cookies is falsy: remove it at final send.
            final_headers = {
                key: value for key, value in (headers or {}).items() if key.lower() != "cookie"
            }
            if cookie:
                final_headers["Cookie"] = cookie
            async with httpx.AsyncClient(verify=True, trust_env=False, timeout=20) as client:
                response = await client.get(url, headers=final_headers, follow_redirects=False)
            received_response = True
            text = response.text
            lowered = text[:65536].lower()
            # Fixed markers classify an explicit challenge; never echo response content.
            challenge = any(
                marker in lowered
                for marker in ("captcha", "verifycenter", "安全验证", "验证码", "滑块验证")
            ) and (
                "html" in response.headers.get("content-type", "").lower()
                or lowered.lstrip().startswith(("<!doctype", "<html"))
            )
            if response.status_code == 429:
                raise ParserFailure("source_rate_limited")
            if challenge:
                raise ParserFailure("source_challenge_required")
            if response.status_code in {401, 403}:
                raise ParserFailure("source_auth_required")
            if not 200 <= response.status_code < 300:
                raise ParserFailure("source_http_error")
            if not text.strip():
                raise ParserFailure("source_empty_response")
            try:
                parsed = json.loads(text)
            except ValueError:
                raise ParserFailure("source_schema_changed") from None
            if not isinstance(parsed, dict):
                raise ParserFailure("source_schema_changed")
            last_error = None
            return text
        except ParserFailure as error:
            last_error = error.code
            raise
        except httpx.TimeoutException:
            last_error = "source_timeout"
            raise ParserFailure(last_error) from None
        except httpx.ProtocolError:
            last_error = "source_protocol_error"
            raise ParserFailure(last_error) from None
        except httpx.RequestError:
            last_error = "source_network_error"
            raise ParserFailure(last_error) from None
        except (ValueError, TypeError):
            last_error = "source_protocol_error"
            raise ParserFailure(last_error) from None

    async def defer_stream_check(**kwargs):
        # Recorder validates each stream destination; upstream must not HEAD/follow redirects.
        return True

    spider.async_req = verified_request
    stream.get_response_status = defer_stream_check
    try:
        room = await spider.get_douyin_web_stream_data(data["source"], cookies=cookie)
        # DLR catches request failures internally: preserve our safe classified cause.
        if last_error:
            return {"error": last_error}
        if not isinstance(room, dict) or type(room.get("status")) is not int:
            return {
                "error": "source_schema_changed" if received_response else "source_parse_failed"
            }
        if room["status"] != 2:
            return {"live": False}
        selected = await stream.get_douyin_stream_url(room, "原画", None)
        if (
            not isinstance(selected, dict)
            or not isinstance(selected.get("record_url"), str)
            or not selected["record_url"]
        ):
            return {"error": "source_schema_changed"}
        return {"live": True, "url": selected["record_url"]}
    except ParserFailure as error:
        return {"error": error.code}
    except ImportError:
        return {"error": "provider_dependencies_missing"}
    except Exception:
        return {"error": last_error or "source_parse_failed"}


def main():
    data = json.loads(sys.stdin.buffer.read(65536))
    root = pathlib.Path(data["checkout"])
    # Bypass src/__init__.py's automatic Node installation. Node must already exist.
    package = types.ModuleType("src")
    package.__path__ = [str(root / "src")]
    package.JS_SCRIPT_PATH = root / "src/javascript"
    sys.modules["src"] = package
    from loguru import logger

    logger.remove()
    quiet = types.ModuleType("src.logger")
    quiet.logger = logger
    quiet.script_path = str(root)
    sys.modules["src.logger"] = quiet
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        result = asyncio.run(resolve(data))
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except ImportError:
        print('{"error":"provider_dependencies_missing"}')
    except Exception:
        print('{"error":"source_parse_failed"}')
