from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from live_review.core.auth import current_admin, require_mutation
from live_review.core.database import get_db
from live_review.modules.identity.models import Admin
from live_review.modules.streamers.models import Streamer
from live_review.modules.streamers.schemas import StreamerCreate, StreamerList, StreamerView

router = APIRouter(prefix="/api/v1/streamers", tags=["streamers"])


@router.post("", response_model=StreamerView, status_code=201)
def create_streamer(
    payload: StreamerCreate,
    admin: Annotated[Admin, Depends(require_mutation)],
    db: Annotated[Session, Depends(get_db)],
):
    row = Streamer(workspace_id=admin.workspace_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("", response_model=StreamerList)
def list_streamers(
    admin: Annotated[Admin, Depends(current_admin)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    query = select(Streamer).where(Streamer.workspace_id == admin.workspace_id)
    count = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(
        query.order_by(Streamer.created_at.desc(), Streamer.id.desc()).limit(limit).offset(offset)
    ).all()
    return {"items": items, "total": count, "limit": limit, "offset": offset}
