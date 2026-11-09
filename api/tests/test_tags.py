"""Tag fetching contracts at the ListenBrainz metadata boundary."""

import asyncio
import datetime as dt

import httpx
from fakeredis import FakeAsyncRedis

from concert_scout.models import Artist, Concert
from concert_scout.sources import listenbrainz


def concerts(*mbids: str) -> list[Concert]:
    return [
        Concert(
            id=mbid, name=mbid, url="https://example.com", artists=[Artist(name=mbid, mbid=mbid)]
        )
        for mbid in mbids
    ]


def ids(count: int, prefix: str = "a") -> list[str]:
    return [f"{prefix}{n}" for n in range(count)]


def metadata(asked: list[list[str]]) -> httpx.MockTransport:
    def respond(request: httpx.Request) -> httpx.Response:
        mbids = request.url.params["artist_mbids"].split(",")
        asked.append(mbids)
        body = [{"artist_mbid": m, "tag": {"artist": [{"tag": f"tag-{m}"}]}} for m in mbids]
        return httpx.Response(200, json=body)

    return httpx.MockTransport(respond)


async def test_a_full_batch_is_asked_for_before_anyone_waits_for_tags() -> None:
    asked: list[list[str]] = []
    async with listenbrainz.make_client(metadata(asked)) as client:
        fetch = listenbrainz.TagFetch(client, FakeAsyncRedis())
        fetch.add(concerts(*ids(listenbrainz.TAG_BATCH_SIZE + 3)))
        await asyncio.sleep(0.05)
        assert [len(batch) for batch in asked] == [listenbrainz.TAG_BATCH_SIZE]

        tags = await fetch.tags()
    assert [len(batch) for batch in asked] == [listenbrainz.TAG_BATCH_SIZE, 3]
    assert tags["a52"] == ["tag-a52"]
    assert len(tags) == listenbrainz.TAG_BATCH_SIZE + 3


async def test_an_artist_is_asked_for_once_and_then_read_from_the_cache() -> None:
    asked: list[list[str]] = []
    redis = FakeAsyncRedis()
    async with listenbrainz.make_client(metadata(asked)) as client:
        first = listenbrainz.TagFetch(client, redis)
        first.add(concerts("x", "y"))
        first.add(concerts("x"))
        await first.tags()

        second = listenbrainz.TagFetch(client, redis)
        second.add(concerts("x", "y", "z"))
        tags = await second.tags()
    assert asked == [["x", "y"], ["z"]]
    assert tags == {"x": ["tag-x"], "y": ["tag-y"], "z": ["tag-z"]}
    assert 0 < await redis.ttl("tags:x") <= listenbrainz.CACHE_TTL.total_seconds()


async def test_a_failed_batch_leaves_only_its_artists_untagged() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        mbids = request.url.params["artist_mbids"].split(",")
        if "b0" in mbids:
            return httpx.Response(503)
        return httpx.Response(
            200, json=[{"artist_mbid": m, "tag": {"artist": [{"tag": "t"}]}} for m in mbids]
        )

    async with listenbrainz.make_client(httpx.MockTransport(respond)) as client:
        fetch = listenbrainz.TagFetch(client, FakeAsyncRedis())
        fetch.add(concerts(*ids(listenbrainz.TAG_BATCH_SIZE)))
        fetch.add(concerts("b0"))
        tags = await fetch.tags()
    assert len(tags) == listenbrainz.TAG_BATCH_SIZE
    assert "b0" not in tags


async def test_closing_cancels_batches_still_out() -> None:
    started = asyncio.Event()

    async def hang(request: httpx.Request) -> httpx.Response:
        started.set()
        await asyncio.sleep(dt.timedelta(minutes=1).total_seconds())
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(hang)
    async with listenbrainz.make_client(transport) as client:
        fetch = listenbrainz.TagFetch(client, FakeAsyncRedis())
        fetch.add(concerts(*ids(listenbrainz.TAG_BATCH_SIZE)))
        await asyncio.wait_for(started.wait(), 1)
        await asyncio.wait_for(fetch.close(), 1)
