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


async def write(redis: Redis, key: str, value: BaseModel, ttl: dt.timedelta) -> None:
    try:
        await redis.set(key, value.model_dump_json(), ex=ttl)
    except RedisError as exc:
        logger.warning("Cache write failed: %s", type(exc).__name__)
