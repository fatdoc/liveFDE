"""Local operator interface; deliberately not an unrestricted HTTP job-creation endpoint."""

import argparse
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from live_review.core.config import get_settings
from live_review.core.database import build_engine
from live_review.core.provider_config import ProviderConfigError
from live_review.integrations.media import MediaError
from live_review.modules.identity.models import Admin
from live_review.modules.jobs.models import Job
from live_review.modules.jobs.service import view
from live_review.workers.job_runner import run_job
from live_review.workers.media_jobs import submit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("submit")
    create.add_argument("--material-id", type=UUID, required=True)
    create.add_argument("--config", type=Path, required=True)
    create.add_argument("--fixture", type=Path)
    create.add_argument(
        "--allow-network",
        action="store_true",
        help="Explicit authorization for this job; default is no network",
    )
    execute = commands.add_parser("run-local")
    execute.add_argument("--job-id", type=UUID, required=True)
    for child in (create, execute):
        child.add_argument("--workspace-id", type=UUID, required=True)
        child.add_argument("--admin-id", type=UUID, required=True)
    args = parser.parse_args(argv)
    settings = get_settings()
    engine = build_engine(settings)
    try:
        with Session(engine) as db:
            actor = db.scalar(
                select(Admin).where(
                    Admin.id == args.admin_id,
                    Admin.workspace_id == args.workspace_id,
                    Admin.active.is_(True),
                )
            )
            if actor is None:
                raise MediaError("actor_not_available")
            if args.command == "submit":
                payload = None
                if args.fixture:
                    if not args.fixture.is_absolute() or args.fixture.resolve() != args.fixture:
                        raise MediaError("fixture_path_invalid")
                    with args.fixture.open("rb") as stream:
                        raw = stream.read(65537)
                    if len(raw) > 65536:
                        raise MediaError("fixture_size_limit")
                    payload = json.loads(raw)
                job = submit(
                    db,
                    settings,
                    workspace_id=args.workspace_id,
                    actor_id=args.admin_id,
                    material_id=args.material_id,
                    config_path=args.config,
                    allow_network=args.allow_network,
                    fixture_payload=payload,
                )
                db.commit()
                print(
                    json.dumps(
                        {"job_id": str(job.id), "status": job.status, "attempt": job.attempt}
                    )
                )
                return
            job = db.scalar(
                select(Job).where(
                    Job.id == args.job_id,
                    Job.workspace_id == args.workspace_id,
                    Job.actor_id == args.admin_id,
                )
            )
            if job is None:
                raise MediaError("job_not_available")
            attempt = job.attempt
        run_job(engine, settings, args.job_id, attempt)
        with Session(engine) as db:
            result = view(db, db.get(Job, args.job_id))
        print(json.dumps(result))
        if result["status"] != "succeeded":
            raise SystemExit(1)
    except (ProviderConfigError, MediaError, ValueError, OSError):
        parser.exit(1, "Media operator request failed; inspect safe job status\n")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
