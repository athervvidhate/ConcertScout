import datetime as dt
import logging
from typing import Any

import httpx
from redis.asyncio import Redis

from concert_scout import cache, limits
from concert_scout.models import SeedArtist
from concert_scout.names import normalize
from concert_scout.sources import http

logger = logging.getLogger(__name__)

BASE_URL = "https://musicbrainz.org/ws/2"
CACHE_TTL = dt.timedelta(days=7)
MIN_SCORE = 95


class MusicBrainzError(Exception):
    """MusicBrainz failed."""


def make_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    return http.make_client(BASE_URL, {"fmt": "json"}, transport)


async def resolve(client: httpx.AsyncClient, redis: Redis, name: str) -> SeedArtist:
    """The Artist a Search names. A name MusicBrainz does not hold comes back with no ID."""
    key = f"seed:{normalize(name)}"
    if cached := await cache.read(redis, key, SeedArtist):
        return cached

    await limits.musicbrainz_call(redis)
    params = {"query": f'artist:"{_escaped(name)}"', "limit": 10}
    try:
        response = await client.get("/artist", params=params)
        response.raise_for_status()
        seed = parse_seed(response.json(), name)
    except httpx.HTTPStatusError as exc:
        raise MusicBrainzError(f"status {exc.response.status_code}") from None
    except httpx.HTTPError as exc:
        raise MusicBrainzError(type(exc).__name__) from None
    except (KeyError, TypeError, ValueError) as exc:
        raise MusicBrainzError(f"unreadable response: {type(exc).__name__}") from None

    await cache.write(redis, key, seed, CACHE_TTL)
    return seed


async def filed_name(client: httpx.AsyncClient, redis: Redis, name: str) -> str:
    """The name an Artist is filed under, for a billing that uses another: Usher Raymond is Usher.

    `artist:` skips aliases, and an alias can be longer than the billing, so this is looser than
    `resolve`. Only a billing with no Spotify page of its own comes here.
    """
    key = f"filed:{normalize(name)}"
    if cached := await cache.read(redis, key, SeedArtist):
        return cached.name

    await limits.musicbrainz_call(redis)
    try:
        response = await client.get("/artist", params={"query": f'alias:"{_escaped(name)}"'})
        response.raise_for_status()
        artists: list[dict[str, Any]] = response.json()["artists"]
    except httpx.HTTPStatusError as exc:
        raise MusicBrainzError(f"status {exc.response.status_code}") from None
    except httpx.HTTPError as exc:
        raise MusicBrainzError(type(exc).__name__) from None
    except (KeyError, TypeError, ValueError) as exc:
        raise MusicBrainzError(f"unreadable response: {type(exc).__name__}") from None

    best = next((a["name"] for a in artists if a["score"] >= MIN_SCORE), name)
    await cache.write(redis, key, SeedArtist(name=best), CACHE_TTL)
    return best


def parse_seed(body: dict[str, Any], name: str) -> SeedArtist:
    """Take the best exact name. "Wednesday" scores below "Wednesday 13", so score alone fails."""
    wanted = normalize(name)
    artists: list[dict[str, Any]] = body["artists"]
    for artist in artists:
        names = [artist["name"], *(a["name"] for a in artist.get("aliases", []))]
        if artist["score"] >= MIN_SCORE and wanted in map(normalize, names):
            tags = [tag["name"] for tag in artist.get("tags", [])]
            return SeedArtist(name=artist["name"], mbid=artist["id"], tags=tags)
    return SeedArtist(name=name)


def _escaped(name: str) -> str:
    return name.replace("\\", "\\\\").replace('"', '\\"')
