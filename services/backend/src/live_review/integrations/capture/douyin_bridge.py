"""Executed by the separately installed pinned DLR environment. JSON pipes only.

No copied upstream source. Import side effects (auto-install and logger sinks) are
replaced before import. DLR's web parser alone is called, never its main loop.
"""

import asyncio
import contextlib
import io
import json
import pathlib
import sys
import types


def main():
    data = json.loads(sys.stdin.buffer.read(65536))
    root = pathlib.Path(data["checkout"])
    # Bypass src/__init__.py's automatic Node installation. Node must be installed.
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

    async def resolve():
        from urllib.parse import urlsplit

        import httpx
        from src import spider, stream

        async def verified_request(url, proxy_addr=None, headers=None, **kwargs):
            parts = urlsplit(url)
            if parts.scheme != "https" or parts.hostname != "live.douyin.com":
                raise ValueError("unexpected_parser_destination")
            async with httpx.AsyncClient(verify=True, trust_env=False, timeout=20) as client:
                response = await client.get(url, headers=headers, follow_redirects=False)
                response.raise_for_status()
                return response.text

        async def defer_stream_check(**kwargs):
            # Do not let upstream HEAD-follow-redirects touch an unchecked stream URL.
            # The controlled recorder validates every destination and HTTP response.
            return True

        spider.async_req = verified_request
        stream.get_response_status = defer_stream_check
        get_douyin_web_stream_data = spider.get_douyin_web_stream_data
        get_douyin_stream_url = stream.get_douyin_stream_url

        room = await get_douyin_web_stream_data(data["source"], cookies=data["cookie"])
        # Upstream defaults missing status to offline: explicitly reject parse failures.
        if not isinstance(room, dict) or "status" not in room:
            return {"error": "source_parse_failed"}
        if room["status"] != 2:
            return {"live": False}
        stream = await get_douyin_stream_url(room, "原画", None)
        if not isinstance(stream, dict) or not stream.get("record_url"):
            return {"error": "source_parse_failed"}
        return {"live": True, "url": stream["record_url"]}

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        result = asyncio.run(resolve())
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print('{"error":"source_parse_failed"}')
