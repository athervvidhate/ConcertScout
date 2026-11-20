import asyncio
import datetime as dt
import logging
from collections.abc import Iterable, Sequence
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import BaseModel
from redis.asyncio import Redis

from concert_scout import cache
from concert_scout.models import Concert, SimilarArtist
from concert_scout.sources import http

logger = logging.getLogger(__name__)

BASE_URL = "https://api.listenbrainz.org/1"
NOT_FOUND = 404
NO_CONTENT = 204
# An unsupported Labs API with one live algorithm, so anything calling it needs a fallback.
SIMILAR_URL = "https://labs.api.listenbrainz.org/similar-artists/json"
ALGORITHM = "session_based_days_9000_session_300_contribution_5_threshold_15_limit_50_skip_30"
TAG_BATCH_SIZE = 50
CACHE_TTL = dt.timedelta(days=7)


class ListenBrainzError(Exception):
    """ListenBrainz failed."""


class UserNotFound(Exception):
    """No ListenBrainz account has that username."""


class CachedSimilar(BaseModel):
    artists: list[SimilarArtist]


class CachedTags(BaseModel):
    tags: list[str]


class ArtistMetadata(BaseModel):
    """MusicBrainz's identity for an Artist, as ListenBrainz relays it. A gap stays None."""

    tags: list[str] = []
    kind: str | None = None
    area: str | None = None


def make_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    return http.make_client(BASE_URL, {}, transport)


async def similar_artists(
    client: httpx.AsyncClient, redis: Redis, mbid: str
) -> list[SimilarArtist]:
    """An Artist's neighbours, closest first. Scores are raw counts, comparable only per Artist."""
    key = f"similar:listenbrainz:{mbid}"
    if cached := await cache.read(redis, key, CachedSimilar):
        return cached.artists

    body = await _get(client, SIMILAR_URL, {"artist_mbids": mbid, "algorithm": ALGORITHM})
    try:
        artists = parse_similar(body)
    except (KeyError, TypeError, ValueError) as exc:
        raise ListenBrainzError(f"unreadable response: {type(exc).__name__}") from None
    await cache.write(redis, key, CachedSimilar(artists=artists), CACHE_TTL)
    return artists


def parse_similar(body: list[dict[str, Any]]) -> list[SimilarArtist]:
    artists = [
        SimilarArtist(name=record["name"], mbid=record["artist_mbid"], score=record["score"])
        for record in body
    ]
    return sorted(artists, key=lambda artist: artist.score, reverse=True)


class TagFetch:
    """Tags by MusicBrainz ID, fetched a batch at a time as Concerts arrive, to overlap the pool.

    A failed batch only leaves its Artists untagged for this Search.
    """

    def __init__(self, client: httpx.AsyncClient, redis: Redis) -> None:
        self._client = client
        self._redis = redis
        self._seen: set[str] = set()
        self._waiting: list[str] = []
        self._batches: list[asyncio.Task[dict[str, list[str]]]] = []

    def add(self, concerts: Iterable[Concert]) -> None:
        for concert in concerts:
            for artist in concert.artists:
                if artist.mbid and artist.mbid not in self._seen:
                    self._seen.add(artist.mbid)
                    self._waiting.append(artist.mbid)
        while len(self._waiting) >= TAG_BATCH_SIZE:
            self._start(self._waiting[:TAG_BATCH_SIZE])
            del self._waiting[:TAG_BATCH_SIZE]

    async def tags(self) -> dict[str, list[str]]:
        """Every Artist added so far. Waits for the batches still out."""
        if self._waiting:
            self._start(self._waiting)
            self._waiting = []
        fetched = await asyncio.gather(*self._batches)
        return {mbid: found for batch in fetched for mbid, found in batch.items()}

    async def close(self) -> None:
        for batch in self._batches:
            batch.cancel()
        await asyncio.gather(*self._batches, return_exceptions=True)

    def _start(self, mbids: Sequence[str]) -> None:
        self._batches.append(asyncio.create_task(self._batch(list(mbids))))

    async def _batch(self, mbids: Sequence[str]) -> dict[str, list[str]]:
        keys = {mbid: f"tags:{mbid}" for mbid in mbids}
        cached = await cache.read_many(self._redis, list(keys.values()), CachedTags)
        tags = {mbid: cached[key].tags for mbid, key in keys.items() if key in cached}
        missing = [mbid for mbid in mbids if mbid not in tags]
        if missing:
            tags |= await _tag_batch(self._client, self._redis, missing)
        return tags


async def _tag_batch(
    client: httpx.AsyncClient, redis: Redis, mbids: Sequence[str]
) -> dict[str, list[str]]:
    params = {"artist_mbids": ",".join(mbids), "inc": "tag"}
    try:
        tags = parse_tags(await _get(client, "/metadata/artist/", params))
    except ListenBrainzError as exc:
        logger.warning("ListenBrainz tags failed: %s", exc)
        return {}
    except (KeyError, TypeError) as exc:
        logger.warning("ListenBrainz tags unreadable: %s", type(exc).__name__)
        return {}
    # An Artist the metadata leaves out has no tags, which is worth remembering too.
    found = {mbid: tags.get(mbid, []) for mbid in mbids}
    values = {f"tags:{mbid}": CachedTags(tags=tags) for mbid, tags in found.items()}
    await cache.write_many(redis, values, CACHE_TTL)
    return found


def parse_tags(body: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        record["artist_mbid"]: [tag["tag"] for tag in record.get("tag", {}).get("artist", [])]
        for record in body
    }


async def artist_metadata(
    client: httpx.AsyncClient, redis: Redis, mbids: Sequence[str]
) -> dict[str, ArtistMetadata]:
    """Type, country and tags, strongest first, by MusicBrainz ID. A failed batch leaves its
    Artists out, so a Sonic Card falls back to what else is known."""
    unique = list(dict.fromkeys(mbids))
    keys = {mbid: f"metadata:{mbid}" for mbid in unique}
    cached = await cache.read_many(redis, list(keys.values()), ArtistMetadata)
    found = {mbid: cached[key] for mbid, key in keys.items() if key in cached}
    missing = [mbid for mbid in unique if mbid not in found]
    for start in range(0, len(missing), TAG_BATCH_SIZE):
        batch = missing[start : start + TAG_BATCH_SIZE]
        params = {"artist_mbids": ",".join(batch), "inc": "tag"}
        try:
            parsed = parse_metadata(await _get(client, "/metadata/artist/", params))
        except ListenBrainzError as exc:
            logger.warning("ListenBrainz metadata failed: %s", exc)
            continue
        except (KeyError, TypeError) as exc:
            logger.warning("ListenBrainz metadata unreadable: %s", type(exc).__name__)
            continue
        # An Artist the metadata leaves out has nothing to say, which is worth remembering too.
        settled = {mbid: parsed.get(mbid, ArtistMetadata()) for mbid in batch}
        await cache.write_many(redis, {keys[m]: v for m, v in settled.items()}, CACHE_TTL)
        found |= settled
    return found


def parse_metadata(body: list[dict[str, Any]]) -> dict[str, ArtistMetadata]:
    parsed: dict[str, ArtistMetadata] = {}
    for record in body:
        tags = sorted(record.get("tag", {}).get("artist", []), key=lambda t: -t.get("count", 0))
        parsed[record["artist_mbid"]] = ArtistMetadata(
            tags=[tag["tag"] for tag in tags],
            kind=record.get("type") or None,
            area=record.get("area") or None,
        )
    return parsed


async def top_artists(client: httpx.AsyncClient, username: str, limit: int) -> list[str]:
    """A person's Artists, most played first. This stays uncached: a Taste is theirs alone."""
    url = f"/stats/user/{quote(username, safe='')}/artists"
    params = {"count": str(limit), "range": "all_time"}
    try:
        response = await client.get(url, params=params)
        if response.status_code == NOT_FOUND:
            raise UserNotFound
        response.raise_for_status()
        # ListenBrainz answers 204 until it has worked out a new account's stats.
        if response.status_code == NO_CONTENT:
            return []
        return [artist["artist_name"] for artist in response.json()["payload"]["artists"]]
    except httpx.HTTPStatusError as exc:
        raise ListenBrainzError(f"status {exc.response.status_code}") from None
    except httpx.HTTPError as exc:
        raise ListenBrainzError(type(exc).__name__) from None
    except (KeyError, TypeError, ValueError) as exc:
        raise ListenBrainzError(f"unreadable response: {type(exc).__name__}") from None


async def _get(client: httpx.AsyncClient, url: str, params: dict[str, str]) -> Any:
    try:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        raise ListenBrainzError(f"status {exc.response.status_code}") from None
    except httpx.HTTPError as exc:
        raise ListenBrainzError(type(exc).__name__) from None
    except ValueError as exc:
        raise ListenBrainzError(f"unreadable response: {type(exc).__name__}") from None
