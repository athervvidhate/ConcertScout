"""Public Artist pages from Spotify's catalog, with the app's own credentials and no account."""

import datetime as dt
import logging
from typing import Any

import httpx
from pydantic import BaseModel
from redis.asyncio import Redis

from concert_scout import cache
from concert_scout.names import normalize
from concert_scout.sources import http

logger = logging.getLogger(__name__)

BASE_URL = "https://api.spotify.com/v1"
TOKEN_URL = "https://accounts.spotify.com/api/token"
CACHE_TTL = dt.timedelta(days=7)
RESULTS = 5


class CachedPage(BaseModel):
    url: str | None


def make_client(
    client_id: str, secret: str, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    client = http.make_client(BASE_URL, {}, transport)
    client.auth = httpx.BasicAuth(client_id, secret)
    return client


async def artist_page(client: httpx.AsyncClient, redis: Redis, name: str) -> str | None:
    """The page of the Artist with exactly this name. A lookalike is worse than no link."""
    key = f"artist:spotify:{normalize(name)}"
    if cached := await cache.read(redis, key, CachedPage):
        return cached.url
    try:
        grant = await client.post(TOKEN_URL, data={"grant_type": "client_credentials"})
        grant.raise_for_status()
        token: str = grant.json()["access_token"]
        response = await client.get(
            "/search",
            params={"q": name, "type": "artist", "limit": RESULTS},
            auth=None,
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        url = exact_page(name, response.json())
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        logger.warning("Spotify catalog failed: %s", type(exc).__name__)
        return None
    await cache.write(redis, key, CachedPage(url=url), CACHE_TTL)
    return url


def exact_page(name: str, body: dict[str, Any]) -> str | None:
    wanted = normalize(name)
    records: list[dict[str, Any]] = body["artists"]["items"]
    pages = (r["external_urls"]["spotify"] for r in records if normalize(r["name"]) == wanted)
    return next(pages, None)
