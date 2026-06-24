from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.artifacts import router as artifacts_router
from app.api.routes.health import router as health_router
from app.api.routes.extras import router as extras_router
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
    # Production guard: refuse to start silently with the placeholder secret.
    if not settings.DEBUG and settings.SECRET_KEY == "change-this-in-production":
        from app.core.logging import get_logger
        get_logger("startup").warning(
            "insecure_default_secret_key",
            detail="SECRET_KEY is the default placeholder — set a real value in production.",
        )
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
    allow_origins=[o.strip() for o in settings.CORS_ALLOW_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── P16: opt-in API-key + rate limiting (no-op unless configured) ─────────────
_OPEN_PATHS = ("/health", "/metrics", "/docs", "/redoc", "/openapi.json")


@app.middleware("http")
async def security_gate(request, call_next):
    from starlette.responses import JSONResponse
    path = request.url.path
    is_open = any(path.startswith(p) for p in _OPEN_PATHS)

    # API key on mutating methods when a key is configured
    if settings.API_KEY and not is_open and request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if request.headers.get("x-api-key") != settings.API_KEY:
            return JSONResponse({"detail": "Invalid or missing X-API-Key"}, status_code=401)

    # Per-IP rate limit via Redis sliding-minute window (fail-open on Redis error)
    if settings.RATE_LIMIT_PER_MIN and not is_open:
        try:
            from app.redis_client import get_redis
            import time
            r = await get_redis()
            key = f"rl:{request.client.host}:{int(time.time() // 60)}"
            n = await r.incr(key)
            if n == 1:
                await r.expire(key, 60)
            if n > settings.RATE_LIMIT_PER_MIN:
                return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        except Exception:
            pass

    return await call_next(request)

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

# Phase 4: one guard enforces tenant ownership on EVERY run-scoped endpoint
# (no per-endpoint hole). No-op in single-tenant "public" mode.
from app.core.auth import enforce_run_ownership
from fastapi import Depends

_owned = [Depends(enforce_run_ownership)]

app.include_router(health_router)
app.include_router(runs_router, dependencies=_owned)
app.include_router(artifacts_router, dependencies=_owned)
app.include_router(observability_router, dependencies=_owned)
app.include_router(inference_router, dependencies=_owned)
app.include_router(extras_router, dependencies=_owned)
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
