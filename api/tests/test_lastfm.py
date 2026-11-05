from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fakeredis import FakeAsyncRedis

from concert_scout.models import SimilarArtist
from concert_scout.sources import lastfm
from tests.conftest import lastfm_similar

Handler = Callable[[httpx.Request], httpx.Response]


async def similar(handler: Handler, redis: FakeAsyncRedis | None = None) -> list[SimilarArtist]:
    async with lastfm.make_client("secret", httpx.MockTransport(handler)) as client:
        return await lastfm.similar_artists(client, redis or FakeAsyncRedis(), "Tyler Childers")


async def test_similar_artists_read_the_string_match_and_an_empty_mbid() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=lastfm_similar("Colter Wall"))

    assert await similar(handler) == [SimilarArtist(name="Colter Wall", mbid=None, score=1.0)]
    params = requests[0].url.params
    assert params["method"] == "artist.getSimilar"
    assert params["artist"] == "Tyler Childers"
    assert (params["api_key"], params["format"]) == ("secret", "json")


async def test_an_artist_last_fm_does_not_know_is_an_empty_answer() -> None:
    body: dict[str, Any] = {"error": 6, "message": "The artist you supplied could not be found"}

    assert await similar(lambda _: httpx.Response(404, json=body)) == []


async def test_results_cache_for_seven_days() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=lastfm_similar("Colter Wall"))

    redis = FakeAsyncRedis()
    await similar(handler, redis)
    await similar(handler, redis)

    assert calls == 1
    assert await redis.ttl("similar:lastfm:tyler childers") == 7 * 86400


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(403, json={"error": 10, "message": "Invalid API key"}),
        httpx.Response(200, json={"unexpected": True}),
        httpx.Response(200, text="<html>"),
    ],
)
async def test_a_failure_raises_without_the_api_key(response: httpx.Response) -> None:
    with pytest.raises(lastfm.LastfmError) as caught:
        await similar(lambda _: response)

    assert "secret" not in str(caught.value)
