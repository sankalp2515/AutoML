from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "AutoML Orchestrator"
    DEBUG: bool = False
    SECRET_KEY: str = "change-this-in-production"

    DATABASE_URL: str = "postgresql+asyncpg://automl:automl@postgres:5432/automl"
    DATABASE_URL_SYNC: str = "postgresql://automl:automl@postgres:5432/automl"

    REDIS_URL: str = "redis://redis:6379/0"

    MLFLOW_TRACKING_URI: str = "http://mlflow:5000"

    LLM_PROVIDER: str = "gemini"  # legacy — chain below takes precedence
    # Fallback chain: tried left-to-right; providers without keys are skipped.
    LLM_FALLBACK_CHAIN: str = "gemini,openrouter,deepseek,groq,ollama"

    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.1-flash-lite"
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "nvidia/nemotron-3.5-content-safety:free"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-v4-flash"
    OLLAMA_URL: str = "http://host.docker.internal:11434"
    OLLAMA_MODEL: str = "llama3.1"
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"

    SANDBOX_URL: str = "http://sandbox:8001"

    DATA_DIR: str = "/data"

    MAX_ITERATIONS: int = 3
    IMPROVEMENT_THRESHOLD: float = 0.02
    SANDBOX_TIMEOUT: int = 300
    # Wall-clock budget for a whole pipeline run (seconds). 0 = no cap. Guards
    # against a run that hangs on external retries/loops (R6).
    MAX_RUN_SECONDS: int = 0
    # Hard guard: reject absurdly wide CSVs (column count). 0 = no cap.
    MAX_DATASET_COLUMNS: int = 2000
    # Comma-separated allowed CORS origins (production should set this explicitly).
    CORS_ALLOW_ORIGINS: str = "http://localhost:3000,http://localhost:3002,http://frontend:3000"

    # Security (P16) — opt-in. When API_KEY is set, mutating requests require the
    # X-API-Key header. Rate limiting applies per-IP via Redis when enabled.
    API_KEY: str = ""
    RATE_LIMIT_PER_MIN: int = 0   # 0 = disabled

    # Multi-tenancy (Phase 4) — opt-in. JSON mapping of api-key → tenant id, e.g.
    # '{"key_abc":"acme","key_xyz":"globex"}'. EMPTY = single-tenant "public" mode
    # (no behavior change). When set, each run is owned by the caller's tenant and
    # cross-tenant access is denied. Per-tenant cap on concurrently active runs
    # (0 = unlimited). USE_JOB_QUEUE routes runs through a durable arq worker
    # instead of an in-process background task (survives API restarts).
    TENANT_API_KEYS: str = ""
    QUOTA_MAX_ACTIVE_RUNS_PER_TENANT: int = 0
    USE_JOB_QUEUE: bool = False

    # Supabase auth (Phase 5) — opt-in. Set SUPABASE_JWT_SECRET (Project Settings →
    # API → JWT Secret) to accept `Authorization: Bearer <supabase access token>`;
    # the authenticated user's id becomes their tenant ("user:<uuid>"). The URL +
    # anon key are for the frontend client. Empty = Supabase auth disabled.
    SUPABASE_JWT_SECRET: str = ""
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_JWT_AUD: str = "authenticated"

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
