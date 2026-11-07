import datetime as dt
from typing import Any

import httpx
from pydantic import BaseModel
from redis.asyncio import Redis

from concert_scout import cache
from concert_scout.models import SimilarArtist
from concert_scout.names import normalize
from concert_scout.sources import http

BASE_URL = "https://ws.audioscrobbler.com/2.0"
CACHE_TTL = dt.timedelta(days=7)
LIMIT = 50
ARTIST_NOT_FOUND = 6
USER_NOT_FOUND = 6
PRIVATE_USER = 17


class LastfmError(Exception):
    """Last.fm failed. The message never holds the request URL, which carries the API key."""


class UserNotFound(Exception):
    """No Last.fm account has that username."""


class PrivateUser(Exception):
    """The account hides its listening."""


class CachedSimilar(BaseModel):
    artists: list[SimilarArtist]


def make_client(
    api_key: str, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    return http.make_client(BASE_URL, {"api_key": api_key, "format": "json"}, transport)


async def similar_artists(
    client: httpx.AsyncClient, redis: Redis, name: str
) -> list[SimilarArtist]:
    """An Artist's neighbours, closest first. Last.fm's `match` runs from 0 to 1."""
    key = f"similar:lastfm:{normalize(name)}"
    if cached := await cache.read(redis, key, CachedSimilar):
        return cached.artists

    params = {"method": "artist.getSimilar", "artist": name, "autocorrect": 1, "limit": LIMIT}
    try:
        response = await client.get("/", params=params)
        body = response.json()
        if body.get("error") == ARTIST_NOT_FOUND:
            artists = []
        else:
            response.raise_for_status()
            artists = parse_similar(body)
    except httpx.HTTPStatusError as exc:
        raise LastfmError(f"status {exc.response.status_code}") from None
    except httpx.HTTPError as exc:
        raise LastfmError(type(exc).__name__) from None
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise LastfmError(f"unreadable response: {type(exc).__name__}") from None

    await cache.write(redis, key, CachedSimilar(artists=artists), CACHE_TTL)
    return artists


async def top_artists(client: httpx.AsyncClient, username: str, limit: int) -> list[str]:
    """A person's Artists, most played first. This stays uncached: a Taste is theirs alone."""
    params = {"method": "user.getTopArtists", "user": username, "limit": limit}
    try:
        response = await client.get("/", params=params)
        body = response.json()
        if body.get("error") == USER_NOT_FOUND:
            raise UserNotFound
        if body.get("error") == PRIVATE_USER:
            raise PrivateUser
        response.raise_for_status()
        return [artist["name"] for artist in body["topartists"]["artist"]]
    except httpx.HTTPStatusError as exc:
        raise LastfmError(f"status {exc.response.status_code}") from None
    except httpx.HTTPError as exc:
        raise LastfmError(type(exc).__name__) from None
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise LastfmError(f"unreadable response: {type(exc).__name__}") from None


def parse_similar(body: dict[str, Any]) -> list[SimilarArtist]:
    records: list[dict[str, Any]] = body["similarartists"]["artist"]
    return [
        SimilarArtist(name=r["name"], mbid=r.get("mbid") or None, score=float(r["match"]))
        for r in records
    ]
