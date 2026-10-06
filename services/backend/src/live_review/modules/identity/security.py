"""Password verification and transaction-safe, shared PostgreSQL rate limits."""

from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from live_review.core.auth import token_hash
from live_review.core.errors import ApiError
from live_review.modules.identity.models import LoginThrottle

hasher = PasswordHasher()
DUMMY_HASH = hasher.hash("not-an-account-password")


def verify_password(encoded: str, password: str) -> bool:
    try:
        return hasher.verify(encoded, password)
    except VerificationError:
        return False


def reserve_attempt(db: Session, settings, username: str, address: str):
    # Lock deterministic bucket order to avoid deadlocks. No proxy header trust.
    now = datetime.now(UTC)
    keys = sorted([token_hash("user:" + username), token_hash("ip:" + address)])
    blocked = False
    for key in keys:
        db.execute(
            insert(LoginThrottle)
            .values(
                bucket=key,
                window_start=now,
                attempts=0,
            )
            .on_conflict_do_nothing()
        )
        bucket = db.scalar(
            select(LoginThrottle)
            .where(
                LoginThrottle.bucket == key,
            )
            .with_for_update()
        )
        if bucket.window_start + timedelta(seconds=settings.login_window_seconds) <= now:
            bucket.window_start, bucket.attempts = now, 0
        if bucket.attempts >= settings.login_limit:
            blocked = True
        else:
            bucket.attempts += 1
    db.commit()  # Persist failed attempts too; works across API processes.
    if blocked:
        raise ApiError(429, "login_throttled", "Try again later")
