import json
from redis.asyncio import Redis
from app.config import get_settings

settings = get_settings()

async def redis_client() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)

async def get_cached(key: str):
    client = await redis_client()
    try:
        value = await client.get(key)
        return json.loads(value) if value else None
    finally:
        await client.aclose()

async def set_cached(key: str, value, ttl: int = 86400):
    client = await redis_client()
    try:
        await client.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
    finally:
        await client.aclose()

async def acquire_answer_lock(session_id: int, turn_id: int) -> bool:
    client = await redis_client()
    try:
        return bool(await client.set(f"interview:answer:{session_id}:{turn_id}", "1", nx=True, ex=120))
    finally:
        await client.aclose()

async def check_redis() -> None:
    client = await redis_client()
    try:
        if not await client.ping():
            raise RuntimeError("Redis 不可用")
    finally:
        await client.aclose()
