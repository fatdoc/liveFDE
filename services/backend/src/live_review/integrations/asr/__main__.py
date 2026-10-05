import argparse
import json
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from live_review.integrations.asr import OfflineFixtureProvider, transcribe
from live_review.integrations.media.files import artifact, controlled_file
from live_review.integrations.media.models import Extraction
from live_review.integrations.media.process import MediaError


def main():
    parser = argparse.ArgumentParser(description="Synthetic offline ASR contract exercise")
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("offline-transcribe")
    command.add_argument("--manifest", type=Path, required=True)
    command.add_argument("--artifact-root", type=Path, required=True)
    command.add_argument("--fixture", type=Path, required=True)
    command.add_argument("--enable-offline-fixture", action="store_true", required=True)
    command.add_argument(
        "--environment", choices=["development", "test", "production"], required=True
    )
    args = parser.parse_args()
    try:
        manifest = controlled_file(args.artifact_root, args.manifest)
        if manifest.stat().st_size > 2 * 1024 * 1024:
            raise MediaError("manifest_size_limit")
        extraction = Extraction.model_validate_json(manifest.read_text())
        provider = OfflineFixtureProvider.from_file(
            args.fixture, enabled=args.enable_offline_fixture, environment=args.environment
        )
        result = transcribe(extraction, artifact_root=args.artifact_root, provider=provider)
        target = manifest.parent / f"transcript-{uuid4().hex}.json"
        target.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "status": result.status,
                    "synthetic": True,
                    "artifact": artifact(args.artifact_root.resolve(), target).to_dict(),
                }
            )
        )
        return 0 if result.complete else 3
    except (MediaError, ValidationError, OSError, ValueError) as error:
        code = error.code if isinstance(error, MediaError) else "invalid_local_input"
        print(json.dumps({"error": {"code": code}}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
