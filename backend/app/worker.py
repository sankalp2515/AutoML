"""arq worker entrypoint (Phase 4, opt-in).

Run a dedicated worker container with:
    arq app.worker.WorkerSettings

It pulls run jobs off the Redis queue and executes the pipeline — decoupled from
the API process, so runs survive API restarts and scale horizontally. Only used
when USE_JOB_QUEUE=true; otherwise the API runs pipelines in-process.
"""

from __future__ import annotations

from arq.connections import RedisSettings

from app.config import settings


async def run_pipeline_job(ctx, run_id: str) -> None:
    from app.agents.orchestrator import run_pipeline
    await run_pipeline(run_id)


class WorkerSettings:
    functions = [run_pipeline_job]
    # arq reads this as a RedisSettings INSTANCE (not a method). Job timeout is
    # generous (a full pipeline run).
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    job_timeout = 3600
    max_jobs = 4
