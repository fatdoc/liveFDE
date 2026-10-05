import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request, Response
from sqlalchemy import delete, select

from live_review.core.auth import (
    COOKIE_NAME,
    CurrentAdmin,
    Database,
    MutationAdmin,
    require_origin,
    token_hash,
)
from live_review.core.errors import ApiError
from live_review.modules.identity.models import Admin, AuthSession
from live_review.modules.identity.schemas import LoginRequest, LoginResponse
from live_review.modules.identity.security import (
    DUMMY_HASH,
    hasher,
    reserve_attempt,
    verify_password,
)

router = APIRouter(prefix="/api/v1/auth", tags=["identity"])


def user_view(admin: Admin):
    return {
        "id": str(admin.id),
        "workspace_id": str(admin.workspace_id),
        "display_name": admin.display_name,
        "role": "admin",
    }


@router.post("/login", response_model=LoginResponse)
def login(data: LoginRequest, request: Request, response: Response, db: Database):
    require_origin(request)
    settings = request.app.state.settings
    reserve_attempt(
        db, settings, data.username, request.client.host if request.client else "unknown"
    )
    admin = db.scalar(select(Admin).where(Admin.username == data.username))
    valid = verify_password(admin.password_hash if admin else DUMMY_HASH, data.password)
    if not valid or not admin or not admin.active:
        raise ApiError(401, "invalid_credentials", "Invalid credentials")
    if hasher.check_needs_rehash(admin.password_hash):
        admin.password_hash = hasher.hash(data.password)
    old_token = request.cookies.get(COOKIE_NAME)
    if old_token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash(old_token)))
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            token_hash=token_hash(token),
            admin_id=admin.id,
            csrf_token=csrf,
            expires_at=datetime.now(UTC) + timedelta(seconds=settings.session_ttl_seconds),
        )
    )
    db.commit()
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.environment == "production",
        path="/",
        max_age=settings.session_ttl_seconds,
    )
    return {"user": user_view(admin), "csrf_token": csrf}


@router.get("/me", response_model=LoginResponse)
def me(request: Request, admin: CurrentAdmin):
    return {"user": user_view(admin), "csrf_token": request.state.auth_session.csrf_token}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, admin: MutationAdmin, db: Database):
    db.delete(request.state.auth_session)
    db.commit()
    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=request.app.state.settings.environment == "production",
    )
