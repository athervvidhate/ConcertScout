import httpx
import pytest
from fakeredis import FakeAsyncRedis

from concert_scout import similarity
from concert_scout.matching import Neighbour
from concert_scout.models import SeedArtist
from concert_scout.sources import lastfm, listenbrainz
from tests.conftest import TYLER_MBID, lastfm_similar, lb_similar

SEED = SeedArtist(name="Tyler Childers", mbid=TYLER_MBID)


async def neighbours(
    labs: httpx.MockTransport,
    last: httpx.MockTransport | None = None,
    seeds: tuple[SeedArtist, ...] = (SEED,),
) -> list[Neighbour]:
    async with listenbrainz.make_client(labs) as client:
        if last is None:
            return await similarity.find_neighbours(client, None, FakeAsyncRedis(), seeds)
        async with lastfm.make_client("key", last) as fallback:
            return await similarity.find_neighbours(client, fallback, FakeAsyncRedis(), seeds)


def labs_down() -> httpx.MockTransport:
    return httpx.MockTransport(lambda _: httpx.Response(404))


def labs_answering(graph: dict[str, list[tuple[str, str]]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=lb_similar(*graph.get(request.url.params["artist_mbids"], []))
        )

    return httpx.MockTransport(handler)


def forbidden() -> httpx.MockTransport:
    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("this source should not be called")

    return httpx.MockTransport(handler)


async def test_two_hops_multiply_the_closeness_along_the_path() -> None:
    graph = {
        TYLER_MBID: [("Sturgill Simpson", "a"), ("Colter Wall", "b")],
        "a": [("Margo Price", "c"), ("Jason Isbell", "d")],
        "b": [("Zach Bryan", "e")],
    }

    found = {(n.name, n.hops): n.closeness for n in await neighbours(labs_answering(graph))}

    assert found[("Sturgill Simpson", 1)] == 1.0
    assert found[("Colter Wall", 1)] == 0.5
    assert found[("Margo Price", 2)] == 1.0
    assert found[("Jason Isbell", 2)] == 0.5
    assert found[("Zach Bryan", 2)] == 0.5


async def test_two_hops_start_from_a_seeds_top_fifteen_only() -> None:
    first_hop = [(f"Artist {n}", f"m{n}") for n in range(20)]
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        mbid = request.url.params["artist_mbids"]
        asked.append(mbid)
        return httpx.Response(200, json=lb_similar(*first_hop) if mbid == TYLER_MBID else [])

    await neighbours(httpx.MockTransport(handler))

    assert len(asked) == 1 + similarity.SECOND_HOP_FROM
    assert "m15" not in asked


async def test_listenbrainz_failing_falls_back_to_last_fm_for_both_hops() -> None:
    names: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        name = request.url.params["artist"]
        names.append(name)
        return httpx.Response(
            200,
            json=lastfm_similar("Colter Wall")
            if name == SEED.name
            else lastfm_similar("Zach Bryan"),
        )

    found = await neighbours(labs_down(), httpx.MockTransport(handler))

    assert sorted(names) == ["Colter Wall", "Tyler Childers"]
    assert [(n.name, n.hops) for n in found] == [("Colter Wall", 1), ("Zach Bryan", 2)]


async def test_an_empty_listenbrainz_answer_also_falls_back() -> None:
    last = httpx.MockTransport(lambda _: httpx.Response(200, json=lastfm_similar("Colter Wall")))

    found = await neighbours(labs_answering({}), last)

    assert [n.name for n in found if n.hops == 1] == ["Colter Wall"]


async def test_a_seed_with_no_id_skips_listenbrainz() -> None:
    seed = SeedArtist(name="Local Band")
    last = httpx.MockTransport(lambda _: httpx.Response(200, json=lastfm_similar("Colter Wall")))

    found = await neighbours(forbidden(), last, (seed,))

    assert found[0].seed == "Local Band"


async def test_listenbrainz_answering_leaves_last_fm_alone() -> None:
    labs = labs_answering({TYLER_MBID: [("Colter Wall", "a")]})

    assert await neighbours(labs, forbidden())


async def test_with_every_source_down_a_seed_simply_has_no_neighbours() -> None:
    last = httpx.MockTransport(lambda _: httpx.Response(404))

    assert await neighbours(labs_down(), last) == []


async def test_with_no_last_fm_key_a_listenbrainz_failure_leaves_no_neighbours() -> None:
    assert await neighbours(labs_down()) == []


async def test_a_failed_second_hop_keeps_the_first() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["artist_mbids"] == TYLER_MBID:
            return httpx.Response(200, json=lb_similar(("Colter Wall", "a")))
        return httpx.Response(404)

    found = await neighbours(httpx.MockTransport(handler))

    assert [n.name for n in found] == ["Colter Wall"]


@pytest.mark.parametrize("count", [1, 2])
def test_closest_prefers_one_hop_and_lists_a_name_once(count: int) -> None:
    def neighbour(name: str, hops: int, closeness: float) -> Neighbour:
        return Neighbour(
            name=name, mbid=None, hops=1 if hops == 1 else 2, closeness=closeness, seed="s"
        )

    ranked = [neighbour("Far", 2, 1.0), neighbour("Near", 1, 0.2), neighbour("Near", 1, 0.1)]

    assert similarity.closest(ranked, count) == ["Near", "Far"][:count]
