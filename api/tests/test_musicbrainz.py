from collections.abc import Callable

import httpx
import pytest
from fakeredis import FakeAsyncRedis

from concert_scout.models import SeedArtist
from concert_scout.sources import http, musicbrainz
from tests.conftest import TYLER_MBID, mb_artist

Handler = Callable[[httpx.Request], httpx.Response]


async def resolve(handler: Handler, name: str, redis: FakeAsyncRedis | None = None) -> SeedArtist:
    async with musicbrainz.make_client(httpx.MockTransport(handler)) as client:
        return await musicbrainz.resolve(client, redis or FakeAsyncRedis(), name)


def answering(*artists: dict[str, object]) -> Handler:
    return lambda _: httpx.Response(200, json={"artists": list(artists)})


async def test_resolve_finds_the_id_and_tags() -> None:
    seed = await resolve(answering(mb_artist()), "tyler childers")

    assert seed.mbid == TYLER_MBID
    assert seed.name == "Tyler Childers"
    assert seed.tags == ["country", "americana", "alternative country"]


async def test_resolve_skips_a_higher_scored_name_that_only_contains_the_search() -> None:
    wrong = mb_artist(id="wrong", name="Wednesday 13", score=100)
    right = mb_artist(id="right", name="Wednesday", score=99)

    assert (await resolve(answering(wrong, right), "Wednesday")).mbid == "right"


async def test_resolve_accepts_an_alias() -> None:
    artist = mb_artist(id="kanye", name="Kanye West", aliases=[{"name": "Ye"}])

    assert (await resolve(answering(artist), "Ye")).mbid == "kanye"


async def test_a_low_score_is_no_match() -> None:
    seed = await resolve(answering(mb_artist(score=90)), "Tyler Childers")

    assert seed == SeedArtist(name="Tyler Childers")


async def test_an_unknown_artist_keeps_the_searched_name_and_is_remembered() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"artists": []})

    redis = FakeAsyncRedis()
    assert await resolve(handler, "Nobody Real", redis) == SeedArtist(name="Nobody Real")
    await resolve(handler, "Nobody Real", redis)

    assert calls == 1


async def test_a_result_caches_for_seven_days() -> None:
    redis = FakeAsyncRedis()
    await resolve(answering(mb_artist()), "Tyler Childers", redis)

    assert await redis.ttl("seed:tyler childers") == 7 * 86400


async def test_the_request_identifies_the_app_with_no_personal_email() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"artists": []})

    await resolve(handler, 'Say "Anything"')

    assert requests[0].headers["user-agent"] == http.USER_AGENT
    assert "github.com" in http.USER_AGENT
    assert "@" not in http.USER_AGENT
    assert requests[0].url.params["query"] == 'artist:"Say \\"Anything\\""'
    assert requests[0].url.params["fmt"] == "json"


@pytest.mark.parametrize("response", [httpx.Response(404), httpx.Response(200, text="not json")])
async def test_a_failure_raises_and_is_not_cached(response: httpx.Response) -> None:
    redis = FakeAsyncRedis()

    with pytest.raises(musicbrainz.MusicBrainzError):
        await resolve(lambda _: response, "Tyler Childers", redis)

    assert await redis.get("seed:tyler childers") is None
