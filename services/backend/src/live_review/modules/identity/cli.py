"""Local operator only: python -m live_review.modules.identity.cli --help."""

import argparse
import getpass
import sys
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from live_review.core.config import get_settings
from live_review.core.database import build_engine
from live_review.modules.identity.models import Admin, Workspace
from live_review.modules.identity.security import hasher


def main():
    parser = argparse.ArgumentParser(
        description="Create an administrator after alembic upgrade head"
    )
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--workspace-name")
    group.add_argument("--workspace-id", type=UUID)
    parser.add_argument("--password-stdin", action="store_true", help="Read one line from stdin")
    args = parser.parse_args()
    password = sys.stdin.readline().rstrip("\r\n") if args.password_stdin else getpass.getpass()
    if not 12 <= len(password) <= 1024:
        parser.error("Password must contain 12 to 1024 characters")
    if not 1 <= len(args.username) <= 100 or not 1 <= len(args.display_name) <= 200:
        parser.error("Invalid username or display name length")
    if args.workspace_name is not None and not 1 <= len(args.workspace_name) <= 200:
        parser.error("Invalid workspace name length")
    engine = build_engine(get_settings())
    try:
        with Session(engine) as db, db.begin():
            if db.scalar(select(Admin.id).where(Admin.username == args.username)):
                parser.error("Username already exists")
            workspace = db.get(Workspace, args.workspace_id) if args.workspace_id else None
            if args.workspace_id and not workspace:
                parser.error("Workspace does not exist")
            if workspace is None:
                workspace = Workspace(name=args.workspace_name)
                db.add(workspace)
                db.flush()
            db.add(
                Admin(
                    workspace_id=workspace.id,
                    username=args.username,
                    display_name=args.display_name,
                    password_hash=hasher.hash(password),
                )
            )
        print("Administrator created")
    except SQLAlchemyError:
        parser.exit(1, "Database operation failed; verify configuration and migrations\n")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
