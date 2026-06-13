from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.artifacts import router as artifacts_router
from app.api.routes.health import router as health_router
from app.api.routes.inference import router as inference_router
from app.api.routes.observability import router as observability_router
from app.api.routes.runs import router as runs_router
from app.api.websocket import router as ws_router
from app.config import settings
from app.core.logging import setup_logging
from app.database import init_db
from app.redis_client import close_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await init_db()
    yield
    await close_redis()


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3002", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus instrumentation MUST attach at import time — middleware cannot be
# added once the app has started (which is what the lifespan does). Previously
# this lived in the lifespan and only "worked" because the package was missing
# and the ImportError was swallowed; with it baked into the image the bug surfaced.
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        excluded_handlers=["/metrics", "/health"],
    ).instrument(app).expose(app, endpoint="/metrics_fastapi", include_in_schema=False)
except ImportError:
    pass

app.include_router(health_router)
app.include_router(runs_router)
app.include_router(artifacts_router)
app.include_router(observability_router)
app.include_router(inference_router)
app.include_router(ws_router)


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """Prometheus scrape endpoint."""
    try:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
    except ImportError:
        return Response(content="# prometheus_client not installed\n", media_type="text/plain")


@app.get("/")
async def root() -> dict:
    return {"service": settings.APP_NAME, "version": "1.0.0", "docs": "/docs"}
