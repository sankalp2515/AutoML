import json
from typing import Any

import redis.asyncio as aioredis

from app.config import settings

_redis_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_pool


async def close_redis() -> None:
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None


async def publish_progress(run_id: str, payload: dict[str, Any]) -> None:
    redis = await get_redis()
    await redis.publish(f"run:{run_id}:progress", json.dumps(payload))


async def set_run_state(run_id: str, state: dict[str, Any]) -> None:
    redis = await get_redis()
    await redis.set(f"run:{run_id}:state", json.dumps(state, default=str), ex=86400)


async def get_run_state(run_id: str) -> dict[str, Any] | None:
    redis = await get_redis()
    raw = await redis.get(f"run:{run_id}:state")
    return json.loads(raw) if raw else None
