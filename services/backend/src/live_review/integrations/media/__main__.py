import argparse
import json
from pathlib import Path

from live_review.integrations.media import MediaError, extract_audio


def main():
    parser = argparse.ArgumentParser(description="Local-only 16 kHz mono WAV extraction")
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("extract")
    command.add_argument("--source", type=Path, required=True)
    command.add_argument("--input-root", type=Path, required=True)
    command.add_argument("--output-root", type=Path, required=True)
    command.add_argument("--segment-seconds", type=int, default=300)
    command.add_argument("--max-duration-seconds", type=int, default=14400)
    command.add_argument("--ffmpeg-timeout-seconds", type=float, default=600)
    command.add_argument("--ffprobe-timeout-seconds", type=float, default=30)
    args = vars(parser.parse_args())
    args.pop("command")
    try:
        result = extract_audio(**args)
        print(result.model_dump_json(indent=2))
        return 0
    except MediaError as error:
        print(json.dumps({"error": {"code": error.code}}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
