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

    LLM_PROVIDER: str = "groq"  # legacy — chain below takes precedence
    # Fallback chain: tried left-to-right; providers without keys are skipped.
    LLM_FALLBACK_CHAIN: str = "groq,gemini,openrouter,deepseek,ollama"

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

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
