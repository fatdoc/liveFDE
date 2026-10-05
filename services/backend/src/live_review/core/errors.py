"""Safe API envelopes; never echo untrusted validation inputs or exceptions."""

from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details=None):
        self.status, self.code, self.message = status, code, message
        self.details = details or {}


def response(request: Request, status: int, code: str, message: str, details=None):
    request_id = getattr(request.state, "request_id", str(uuid4()))
    return JSONResponse(
        {
            "code": code,
            "message": message,
            "request_id": request_id,
            "details": details or {},
        },
        status_code=status,
        headers={"Cache-Control": "private,no-store", "X-Request-ID": request_id},
    )


def install_errors(app: FastAPI):
    @app.middleware("http")
    async def request_context(request, call_next):
        request.state.request_id = str(uuid4())
        result = await call_next(request)
        result.headers["X-Request-ID"] = request.state.request_id
        if request.url.path.startswith("/api/"):
            result.headers["Cache-Control"] = "private,no-store"
        return result

    @app.exception_handler(ApiError)
    async def business_error(request, exc):
        return response(request, exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return response(request, 422, "validation_error", "Invalid request fields")

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return response(request, exc.status_code, "http_error", "Request rejected")

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        return response(request, 503, "dependency_unavailable", "Service unavailable")

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        return response(request, 500, "internal_error", "Internal service error")
