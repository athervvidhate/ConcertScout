import datetime as dt

from fakeredis import FakeAsyncRedis
from redis.exceptions import ConnectionError

from concert_scout import cache
from concert_scout.models import Place
from tests.conftest import CHICAGO

TTL = dt.timedelta(minutes=1)


class BrokenRedis(FakeAsyncRedis):
    async def execute_command(self, *_: object, **__: object) -> None:
        raise ConnectionError


async def test_a_written_value_reads_back_and_expires() -> None:
    redis = FakeAsyncRedis()

    await cache.write(redis, "key", CHICAGO, TTL)

    assert await cache.read(redis, "key", Place) == CHICAGO
    assert 0 < await redis.ttl("key") <= TTL.total_seconds()


async def test_a_missing_key_reads_as_none() -> None:
    assert await cache.read(FakeAsyncRedis(), "key", Place) is None


async def test_a_value_of_an_old_shape_counts_as_a_miss() -> None:
    redis = FakeAsyncRedis()
    await redis.set("key", '{"unexpected": true}')

    assert await cache.read(redis, "key", Place) is None


async def test_a_redis_outage_never_raises() -> None:
    redis = BrokenRedis()

    await cache.write(redis, "key", CHICAGO, TTL)

    assert await cache.read(redis, "key", Place) is None


async def test_many_values_write_and_read_back_in_one_go() -> None:
    redis = FakeAsyncRedis()

    await cache.write_many(redis, {"a": CHICAGO, "b": CHICAGO}, TTL)

    assert await cache.read_many(redis, ["a", "b", "missing"], Place) == {
        "a": CHICAGO,
        "b": CHICAGO,
    }
    assert 0 < await redis.ttl("b") <= TTL.total_seconds()


async def test_reading_no_keys_asks_redis_for_nothing() -> None:
    assert await cache.read_many(BrokenRedis(), [], Place) == {}


async def test_a_redis_failure_reads_many_as_all_misses() -> None:
    assert await cache.read_many(BrokenRedis(), ["a"], Place) == {}
