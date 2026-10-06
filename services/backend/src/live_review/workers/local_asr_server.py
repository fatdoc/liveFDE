"""Explicit local ASR worker CLI; does not install dependencies or download models."""

import argparse
import asyncio
import json
import os
import signal
import stat
from pathlib import Path

from live_review.integrations.asr_gateway.local_worker.server import LocalWorkerServer


def load_config(path):
    from live_review.integrations.asr_gateway.local import LocalConfig

    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError("worker_config_file_invalid")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd) as source:
        info = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_size > 16384
        ):
            raise ValueError("worker_config_file_invalid")
        return LocalConfig.model_validate(json.load(source))


async def serve(args):
    from live_review.integrations.asr_gateway.local import LocalASRProvider, unload_local_models

    config = load_config(args.config_json)
    server = LocalWorkerServer(
        args.socket, config, args.storage_root, LocalASRProvider(config), unload_local_models
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for event in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(event, stop.set)
    await server.start()
    try:
        await stop.wait()
    finally:
        await server.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-json", required=True)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--storage-root", required=True)
    args = parser.parse_args()
    try:
        asyncio.run(serve(args))
    except Exception:
        raise SystemExit("local_asr_worker_start_failed") from None


if __name__ == "__main__":
    main()
