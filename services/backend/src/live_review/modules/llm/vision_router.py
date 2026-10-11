from fastapi import APIRouter, Request

from live_review.core.auth import CurrentAdmin, MutationAdmin
from live_review.modules.llm.schemas import Revision
from live_review.modules.llm.vision_schemas import Public, Update
from live_review.modules.llm.vision_store import Store

router = APIRouter(prefix="/api/v1/llm/vision/settings", tags=["llm"])


@router.get("", response_model=Public)
def read_settings(request: Request, admin: CurrentAdmin):
    return Store(request.app.state.settings, admin.workspace_id).read()


@router.put("", response_model=Public)
def save_settings(data: Update, request: Request, admin: MutationAdmin):
    return Store(request.app.state.settings, admin.workspace_id).update(
        data, revision=data.expected_revision
    )


@router.delete("", response_model=Public)
def clear_settings(data: Revision, request: Request, admin: MutationAdmin):
    return Store(request.app.state.settings, admin.workspace_id).update(
        revision=data.expected_revision
    )
