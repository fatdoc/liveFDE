from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from live_review.core.auth import CurrentAdmin, Database, MutationAdmin
from live_review.core.errors import ApiError
from live_review.integrations.storage.local import LocalStorage
from live_review.modules.materials.models import Blob, Material, SessionMaterial
from live_review.modules.materials.ranges import UnsatisfiableRange, select_range
from live_review.modules.materials.schemas import (
    FinalizeOutput,
    LinkInput,
    LinkOutput,
    MaterialOutput,
    ReceiveOutput,
    SessionMaterialsPage,
    UploadInput,
    UploadOutput,
)
from live_review.modules.materials.service import create_upload, get_material, material_json
from live_review.modules.materials.transfer import finalize, receive
from live_review.modules.sessions.models import LiveSession

router = APIRouter(tags=["materials"])


@router.post("/materials/uploads", status_code=201, response_model=UploadOutput)
def initialize(
    payload: UploadInput,
    request: Request,
    admin: MutationAdmin,
    db: Database,
    idempotency_key: str = Header(default=""),
):
    LocalStorage(request.app.state.settings.storage_root)
    return create_upload(db, admin, payload, idempotency_key, request.app.state.settings)


@router.put("/materials/uploads/{upload_id}/content", response_model=ReceiveOutput)
async def put_content(
    upload_id: UUID,
    request: Request,
    admin: MutationAdmin,
    db: Database,
):
    return await receive(request, db, admin, upload_id)


@router.post("/materials/uploads/{upload_id}/finalize", response_model=FinalizeOutput)
def finish(
    upload_id: UUID,
    request: Request,
    admin: MutationAdmin,
    db: Database,
):
    return finalize(request, db, admin, upload_id)


@router.get("/materials/{material_id}", response_model=MaterialOutput)
def metadata(material_id: UUID, admin: CurrentAdmin, db: Database):
    return material_json(*get_material(db, material_id, admin))


def read_chunks(path, start, count):
    with path.open("rb") as stream:
        stream.seek(start)
        while count:
            chunk = stream.read(min(count, 1024 * 1024))
            if not chunk:
                return
            count -= len(chunk)
            yield chunk


@router.get("/materials/{material_id}/content", operation_id="get_material_content")
@router.head("/materials/{material_id}/content", operation_id="head_material_content")
def content(material_id: UUID, request: Request, admin: CurrentAdmin, db: Database):
    # Authorization must precede filesystem metadata, ETag, and Range interpretation.
    _, blob = get_material(db, material_id, admin)
    path = LocalStorage(request.app.state.settings.storage_root).path("blobs", blob.storage_key)
    if not path.is_file() or path.stat().st_size != blob.size_bytes:
        raise ApiError(503, "blob_unavailable", "材料文件暂不可读取")
    etag = f'"{blob.sha256}"'
    headers = {
        "ETag": etag,
        "Accept-Ranges": "bytes",
        "Cache-Control": "private,no-store",
        "Content-Type": blob.media_type,
        "X-Content-Type-Options": "nosniff",
    }
    try:
        selected = select_range(
            request.headers.get("range") if request.method == "GET" else None,
            blob.size_bytes,
            request.headers.get("if-range"),
            etag,
        )
    except UnsatisfiableRange:
        return Response(
            status_code=416, headers=headers | {"Content-Range": f"bytes */{blob.size_bytes}"}
        )
    start, end = selected if selected else (0, blob.size_bytes - 1)
    headers["Content-Length"] = str(end - start + 1)
    if selected:
        headers["Content-Range"] = f"bytes {start}-{end}/{blob.size_bytes}"
    status = 206 if selected else 200
    if request.method == "HEAD":
        return Response(status_code=status, headers=headers)
    return StreamingResponse(
        read_chunks(path, start, end - start + 1), status_code=status, headers=headers
    )


@router.post("/sessions/{session_id}/materials", status_code=201, response_model=LinkOutput)
def associate(
    session_id: UUID,
    payload: LinkInput,
    response: Response,
    admin: MutationAdmin,
    db: Database,
):
    from live_review.modules.materials.association import associate_material

    result = associate_material(db, admin, session_id, payload)
    if result["already_linked"]:
        response.status_code = 200
    return result


@router.get("/sessions/{session_id}/materials", response_model=SessionMaterialsPage)
def list_associated(
    session_id: UUID,
    admin: CurrentAdmin,
    db: Database,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    session = db.scalar(
        select(LiveSession).where(
            LiveSession.id == session_id, LiveSession.workspace_id == admin.workspace_id
        )
    )
    if session is None:
        raise ApiError(404, "not_found", "场次不存在")
    predicate = (
        SessionMaterial.workspace_id == admin.workspace_id,
        SessionMaterial.session_id == session_id,
    )
    total = db.scalar(select(func.count()).select_from(SessionMaterial).where(*predicate))
    rows = db.execute(
        select(SessionMaterial, Material, Blob)
        .join(
            Material,
            (Material.id == SessionMaterial.material_id)
            & (Material.workspace_id == SessionMaterial.workspace_id),
        )
        .join(Blob, (Blob.id == Material.blob_id) & (Blob.workspace_id == Material.workspace_id))
        .where(*predicate)
        .order_by(Material.created_at.desc(), SessionMaterial.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return {
        "items": [
            {
                "association_id": str(link.id),
                "role": link.role,
                "material": material_json(material, blob),
            }
            for link, material, blob in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
