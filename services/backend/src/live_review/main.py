from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from live_review.core.config import get_settings
from live_review.core.database import build_engine
from live_review.core.errors import install_errors
from live_review.core.health import dependencies_ready
from live_review.modules.asr.router import router as asr_router
from live_review.modules.identity.router import router as identity_router
from live_review.modules.jobs.router import router as jobs_router
from live_review.modules.materials.router import router as materials_router
from live_review.modules.sessions.router import router as sessions_router
from live_review.modules.streamers.router import router as streamers_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = get_settings()
    app.state.engine = build_engine(app.state.settings)
    yield
    app.state.engine.dispose()


app = FastAPI(title="Live Review Foundation", version="0.1.0", lifespan=lifespan)

install_errors(app)
app.include_router(identity_router)
app.include_router(asr_router)
app.include_router(jobs_router)
app.include_router(streamers_router)
app.include_router(sessions_router)
app.include_router(materials_router, prefix="/api/v1")


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
