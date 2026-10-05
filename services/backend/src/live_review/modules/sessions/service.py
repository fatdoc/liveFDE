from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from live_review.core.errors import ApiError
from live_review.modules.sessions.models import LiveSession
from live_review.modules.sessions.schemas import SessionCreate, SessionPatch
from live_review.modules.streamers.models import Streamer


def require_streamer(db: Session, workspace_id: UUID, streamer_id: UUID) -> None:
    if (
        db.scalar(
            select(Streamer.id).where(
                Streamer.id == streamer_id, Streamer.workspace_id == workspace_id
            )
        )
        is None
    ):
        raise ApiError(404, "not_found", "Streamer not found")


def get_session(
    db: Session, workspace_id: UUID, session_id: UUID, *, for_update: bool = False
) -> LiveSession:
    query = select(LiveSession).where(
        LiveSession.id == session_id, LiveSession.workspace_id == workspace_id
    )
    if for_update:
        query = query.with_for_update()
    row = db.scalar(query)
    if row is None:
        raise ApiError(404, "not_found", "Session not found")
    return row


def create_session(db: Session, workspace_id: UUID, payload: SessionCreate) -> LiveSession:
    require_streamer(db, workspace_id, payload.streamer_id)
    row = LiveSession(workspace_id=workspace_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def patch_session(
    db: Session, workspace_id: UUID, session_id: UUID, payload: SessionPatch
) -> LiveSession:
    row = get_session(db, workspace_id, session_id, for_update=True)
    if row.revision != payload.expected_revision:
        raise ApiError(
            409,
            "revision_conflict",
            "Session changed; reload before saving",
            {"current_revision": row.revision},
        )
    changes = payload.model_dump(exclude_unset=True, exclude={"expected_revision"})
    current = {name: getattr(row, name) for name in SessionCreate.model_fields}
    try:
        validated = SessionCreate.model_validate(current | changes)
    except ValidationError as exc:
        raise ApiError(422, "invalid_session_time", "Session fields are inconsistent") from exc
    require_streamer(db, workspace_id, validated.streamer_id)
    for key, value in changes.items():
        setattr(row, key, value)
    if {"session_local_date", "started_at", "time_precision"} & changes.keys():
        row.time_source = "user_entered"
    row.revision += 1
    row.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
    return row
