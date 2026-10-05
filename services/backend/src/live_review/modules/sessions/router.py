from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from live_review.core.auth import current_admin, require_mutation
from live_review.core.database import get_db
from live_review.core.errors import ApiError
from live_review.modules.identity.models import Admin
from live_review.modules.sessions import service
from live_review.modules.sessions.models import LiveSession
from live_review.modules.sessions.schemas import (
    SessionCreate,
    SessionList,
    SessionPatch,
    SessionView,
)
from live_review.modules.streamers.schemas import Platform

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.post("", response_model=SessionView, status_code=201)
def create_session(
    payload: SessionCreate,
    admin: Annotated[Admin, Depends(require_mutation)],
    db: Annotated[Session, Depends(get_db)],
):
    return service.create_session(db, admin.workspace_id, payload)


@router.get("/{session_id}", response_model=SessionView)
def get_session(
    session_id: UUID,
    admin: Annotated[Admin, Depends(current_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    return service.get_session(db, admin.workspace_id, session_id)


@router.patch("/{session_id}", response_model=SessionView)
def patch_session(
    session_id: UUID,
    payload: SessionPatch,
    admin: Annotated[Admin, Depends(require_mutation)],
    db: Annotated[Session, Depends(get_db)],
):
    return service.patch_session(db, admin.workspace_id, session_id, payload)


@router.get("", response_model=SessionList)
def list_sessions(
    admin: Annotated[Admin, Depends(current_admin)],
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str | None, Query(max_length=100)] = None,
    streamer_id: UUID | None = None,
    platform: Platform | None = None,
    status: Literal["pending", "queued", "running", "failed", "succeeded"] | None = None,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    if from_date and to_date and to_date <= from_date:
        raise ApiError(422, "invalid_date_range", "Date range must be nonempty")
    query = select(LiveSession).where(LiveSession.workspace_id == admin.workspace_id)
    if q:
        query = query.where(LiveSession.title.icontains(q, autoescape=True))
    if streamer_id:
        query = query.where(LiveSession.streamer_id == streamer_id)
    if platform:
        query = query.where(LiveSession.platform == platform)
    if status:
        query = query.where(LiveSession.processing_status == status)
    if from_date:
        query = query.where(LiveSession.session_local_date >= from_date)
    if to_date:
        query = query.where(LiveSession.session_local_date < to_date)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(
        query.order_by(LiveSession.created_at.desc(), LiveSession.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}
