from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from live_review.core.errors import ApiError
from live_review.modules.materials.models import SessionMaterial
from live_review.modules.materials.service import get_material
from live_review.modules.sessions.models import LiveSession


def associate_material(db, admin, session_id, payload):
    session = db.scalar(
        select(LiveSession).where(
            LiveSession.id == session_id, LiveSession.workspace_id == admin.workspace_id
        )
    )
    if session is None:
        raise ApiError(404, "not_found", "场次不存在")
    material, _ = get_material(db, payload.material_id, admin)
    if material.purpose == "reference_pdf" and payload.role != "reference":
        raise ApiError(422, "reference_only", "PDF仅能作为参考资料关联")
    relation = SessionMaterial(
        workspace_id=admin.workspace_id,
        session_id=session_id,
        material_id=payload.material_id,
        role=payload.role,
    )
    try:
        with db.begin_nested():
            db.add(relation)
            db.flush()
        already = False
    except IntegrityError:
        relation = db.scalar(
            select(SessionMaterial).where(
                SessionMaterial.workspace_id == admin.workspace_id,
                SessionMaterial.session_id == session_id,
                SessionMaterial.material_id == payload.material_id,
                SessionMaterial.role == payload.role,
            )
        )
        if relation is None:
            raise
        already = True
    db.commit()
    return {
        "session_id": str(session_id),
        "material_id": str(payload.material_id),
        "role": payload.role,
        "already_linked": already,
    }
