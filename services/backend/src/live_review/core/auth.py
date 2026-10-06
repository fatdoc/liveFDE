"""Shared administrator authentication and mutation dependencies."""

import hashlib
import secrets
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from live_review.core.database import get_db
from live_review.core.errors import ApiError
from live_review.modules.identity.models import Admin, AuthSession

COOKIE_NAME = "live_session"
Database = Annotated[Session, Depends(get_db)]


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def require_origin(request: Request):
    if request.headers.get("origin") not in request.app.state.settings.trusted_origins:
        raise ApiError(403, "origin_rejected", "Trusted Origin required")
    site = request.headers.get("sec-fetch-site")
    if site is not None and site != "same-origin":
        raise ApiError(403, "origin_rejected", "Same-origin request required")


def current_admin(request: Request, db: Database) -> Admin:
    token = request.cookies.get(COOKIE_NAME, "")
    auth = db.get(AuthSession, token_hash(token)) if token else None
    admin = db.get(Admin, auth.admin_id) if auth else None
    if not auth or auth.expires_at <= datetime.now(UTC) or not admin or not admin.active:
        raise ApiError(401, "authentication_required", "Authentication required")
    request.state.auth_session = auth
    return admin


CurrentAdmin = Annotated[Admin, Depends(current_admin)]


def require_mutation(request: Request, admin: CurrentAdmin) -> Admin:
    require_origin(request)
    supplied = request.headers.get("x-csrf-token", "")
    if not supplied.isascii() or not secrets.compare_digest(
        supplied, request.state.auth_session.csrf_token
    ):
        raise ApiError(403, "csrf_rejected", "Valid CSRF token required")
    return admin


MutationAdmin = Annotated[Admin, Depends(require_mutation)]
