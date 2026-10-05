from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from live_review.core.config import get_settings
from live_review.core.database import build_engine
from live_review.core.health import dependencies_ready


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = get_settings()
    app.state.engine = build_engine(app.state.settings)
    yield
    app.state.engine.dispose()


app = FastAPI(title="Live Review Foundation", version="0.1.0", lifespan=lifespan)


@app.get("/health/live")
def live():
    return {"status": "alive"}


@app.get("/health/ready")
def ready():
    checks = dependencies_ready(app.state.engine, app.state.settings.broker_url.get_secret_value())
    healthy = all(value == "up" for value in checks.values())
    return JSONResponse(
        {"status": "ready" if healthy else "not_ready", "checks": checks},
        status_code=200 if healthy else 503,
    )
