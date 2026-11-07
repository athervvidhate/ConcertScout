from collections.abc import Callable

import httpx
import pytest
from fakeredis import FakeAsyncRedis

from concert_scout.sources import listenbrainz
from tests.conftest import lb_metadata, lb_similar

Handler = Callable[[httpx.Request], httpx.Response]


async def similar(handler: Handler, redis: FakeAsyncRedis | None = None) -> list[str]:
    async with listenbrainz.make_client(httpx.MockTransport(handler)) as client:
        artists = await listenbrainz.similar_artists(client, redis or FakeAsyncRedis(), "seed")
    return [artist.name for artist in artists]


async def tags(
    handler: Handler, mbids: list[str], redis: FakeAsyncRedis | None = None
) -> dict[str, list[str]]:
    async with listenbrainz.make_client(httpx.MockTransport(handler)) as client:
        return await listenbrainz.artist_tags(client, redis or FakeAsyncRedis(), mbids)


async def test_similar_artists_come_closest_first_from_the_labs_host() -> None:
    requests: list[httpx.Request] = []
    body = list(reversed(lb_similar(("Sturgill Simpson", "a"), ("Colter Wall", "b"))))

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=body)

    assert await similar(handler) == ["Sturgill Simpson", "Colter Wall"]
    assert requests[0].url.host == "labs.api.listenbrainz.org"
    assert requests[0].url.params["artist_mbids"] == "seed"
    assert requests[0].url.params["algorithm"] == listenbrainz.ALGORITHM


async def test_similar_artists_cache_for_seven_days_even_when_empty() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=[])

    redis = FakeAsyncRedis()
    await similar(handler, redis)
    await similar(handler, redis)

    assert calls == 1
    assert await redis.ttl("similar:listenbrainz:seed") == 7 * 86400


@pytest.mark.parametrize(
    "response",
    [httpx.Response(404), httpx.Response(200, text="<html>"), httpx.Response(200, json=[{}])],
)
async def test_a_similar_failure_raises_and_is_not_cached(response: httpx.Response) -> None:
    redis = FakeAsyncRedis()

    with pytest.raises(listenbrainz.ListenBrainzError):
        await similar(lambda _: response, redis)

    assert await redis.get("similar:listenbrainz:seed") is None


async def test_tags_arrive_in_batches_of_fifty() -> None:
    mbids = [f"m{n}" for n in range(120)]
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        wanted = request.url.params["artist_mbids"].split(",")
        return httpx.Response(200, json=lb_metadata(**{mbid: ["americana"] for mbid in wanted}))

    found = await tags(handler, mbids)

    assert sorted(len(r.url.params["artist_mbids"].split(",")) for r in requests) == [20, 50, 50]
    assert all(r.url.params["inc"] == "tag" for r in requests)
    assert found["m119"] == ["americana"]


async def test_cached_tags_are_not_fetched_again_and_last_seven_days() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=lb_metadata(a=["folk"]))

    redis = FakeAsyncRedis()
    await tags(handler, ["a", "untagged"], redis)
    found = await tags(handler, ["a", "untagged"], redis)

    assert len(requests) == 1
    assert found == {"a": ["folk"], "untagged": []}
    assert await redis.ttl("tags:a") == 7 * 86400


async def test_a_failed_tag_batch_leaves_the_others_and_is_not_cached() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        wanted = request.url.params["artist_mbids"].split(",")
        if "m0" in wanted:
            return httpx.Response(404)
        return httpx.Response(200, json=lb_metadata(**{mbid: ["folk"] for mbid in wanted}))

    redis = FakeAsyncRedis()
    found = await tags(handler, [f"m{n}" for n in range(60)], redis)

    assert len(found) == 10
    assert await redis.get("tags:m0") is None
