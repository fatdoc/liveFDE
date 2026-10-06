from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from live_review.core.config import Settings


class Base(DeclarativeBase):
    pass


def build_engine(settings: Settings):
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"},
    )


def get_db(request: Request):
    """Shared request session; business services commit their own transactions."""
    with Session(request.app.state.engine, expire_on_commit=False) as session:
        yield session
