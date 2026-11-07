import asyncio
import datetime as dt
import logging
from collections.abc import Sequence
from itertools import batched
from typing import Any

import httpx
from pydantic import BaseModel
from redis.asyncio import Redis

from concert_scout import cache
from concert_scout.models import SimilarArtist
from concert_scout.sources import http

logger = logging.getLogger(__name__)

BASE_URL = "https://api.listenbrainz.org/1"
# An unsupported Labs API with one live algorithm, so anything calling it needs a fallback.
SIMILAR_URL = "https://labs.api.listenbrainz.org/similar-artists/json"
ALGORITHM = "session_based_days_9000_session_300_contribution_5_threshold_15_limit_50_skip_30"
TAG_BATCH_SIZE = 50
CACHE_TTL = dt.timedelta(days=7)


class ListenBrainzError(Exception):
    """ListenBrainz failed."""


class CachedSimilar(BaseModel):
    artists: list[SimilarArtist]


class CachedTags(BaseModel):
    tags: list[str]


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


async def artist_tags(
    client: httpx.AsyncClient, redis: Redis, mbids: Sequence[str]
) -> dict[str, list[str]]:
    """Tags by MusicBrainz ID. A failed batch only leaves its Artists untagged for this Search."""
    keys = {mbid: f"tags:{mbid}" for mbid in mbids}
    cached = await cache.read_many(redis, list(keys.values()), CachedTags)
    tags = {mbid: cached[key].tags for mbid, key in keys.items() if key in cached}

    missing = [mbid for mbid in keys if mbid not in tags]
    batches = batched(missing, TAG_BATCH_SIZE, strict=False)
    fetched = await asyncio.gather(*(_tag_batch(client, redis, batch) for batch in batches))
    return tags | {mbid: found for batch in fetched for mbid, found in batch.items()}


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
