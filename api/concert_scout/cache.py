import datetime as dt
import logging

from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


def make_client(url: str) -> Redis:
    return Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
        url, socket_timeout=1.0, socket_connect_timeout=1.0
    )


# A cache failure only costs a repeat call, so it counts as a miss and never fails a Search.
async def read[T: BaseModel](redis: Redis, key: str, model: type[T]) -> T | None:
    try:
        cached = await redis.get(key)
        return model.model_validate_json(cached) if cached else None
    except (RedisError, ValidationError) as exc:
        logger.warning("Cache read failed: %s", type(exc).__name__)
        return None


async def read_many[T: BaseModel](redis: Redis, keys: list[str], model: type[T]) -> dict[str, T]:
    """The keys that hit. One Search can hold hundreds, so this is a single round trip."""
    if not keys:
        return {}
    try:
        values = await redis.mget(keys)
        return {k: model.model_validate_json(v) for k, v in zip(keys, values, strict=True) if v}
    except (RedisError, ValidationError) as exc:
        logger.warning("Cache read failed: %s", type(exc).__name__)
        return {}


async def write(redis: Redis, key: str, value: BaseModel, ttl: dt.timedelta) -> None:
    try:
        await redis.set(key, value.model_dump_json(), ex=ttl)
    except RedisError as exc:
        logger.warning("Cache write failed: %s", type(exc).__name__)


async def write_many(redis: Redis, values: dict[str, BaseModel], ttl: dt.timedelta) -> None:
    try:
        async with redis.pipeline(transaction=False) as pipeline:
            for key, value in values.items():
                pipeline.set(key, value.model_dump_json(), ex=ttl)
            await pipeline.execute()
    except RedisError as exc:
        logger.warning("Cache write failed: %s", type(exc).__name__)
