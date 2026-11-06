import datetime as dt
from typing import Any

import httpx
from redis.asyncio import Redis

from concert_scout import cache
from concert_scout.models import Place, Places
from concert_scout.sources import http

BASE_URL = "https://api.geoapify.com/v1/geocode"
CACHE_TTL = dt.timedelta(days=30)


class GeocoderError(Exception):
    """Geoapify failed. The message never holds the request URL, which carries the API key."""


def make_client(
    api_key: str, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    return http.make_client(BASE_URL, {"apiKey": api_key}, transport)


async def geocode(client: httpx.AsyncClient, redis: Redis, text: str) -> Place | None:
    places = await find_places(client, redis, text, limit=1)
    return places[0] if places else None


async def find_places(
    client: httpx.AsyncClient, redis: Redis, text: str, limit: int = 5
) -> list[Place]:
    key = f"geocode:{limit}:{' '.join(text.casefold().split())}"
    if cached := await cache.read(redis, key, Places):
        return cached.places

    # `locality` covers cities, districts, counties and states, but not streets or venues.
    params = {"text": text, "type": "locality", "limit": limit, "format": "json"}
    try:
        response = await client.get("/autocomplete", params=params)
        response.raise_for_status()
        places = parse_places(response.json())
    except httpx.HTTPStatusError as exc:
        raise GeocoderError(f"status {exc.response.status_code}") from None
    except httpx.HTTPError as exc:
        raise GeocoderError(type(exc).__name__) from None
    except (KeyError, TypeError, ValueError) as exc:
        raise GeocoderError(f"unreadable response: {type(exc).__name__}") from None

    if places:
        await cache.write(redis, key, Places(places=places), CACHE_TTL)
    return places


def parse_places(body: dict[str, Any]) -> list[Place]:
    results: list[dict[str, Any]] = body.get("results", [])
    return [Place(name=r["formatted"], lat=r["lat"], lon=r["lon"]) for r in results]
