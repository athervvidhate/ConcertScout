import datetime as dt
from typing import Any

import httpx
from redis.asyncio import Redis

from concert_scout import cache
from concert_scout.models import Place
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
    key = f"geocode:{' '.join(text.casefold().split())}"
    if cached := await cache.read(redis, key, Place):
        return cached

    # `locality` covers cities, districts, counties and states, but not streets or venues.
    params = {"text": text, "type": "locality", "limit": 1, "format": "json"}
    try:
        response = await client.get("/autocomplete", params=params)
        response.raise_for_status()
        place = parse_place(response.json())
    except httpx.HTTPStatusError as exc:
        raise GeocoderError(f"status {exc.response.status_code}") from None
    except httpx.HTTPError as exc:
        raise GeocoderError(type(exc).__name__) from None
    except (KeyError, TypeError, ValueError) as exc:
        raise GeocoderError(f"unreadable response: {type(exc).__name__}") from None

    if place:
        await cache.write(redis, key, place, CACHE_TTL)
    return place


def parse_place(body: dict[str, Any]) -> Place | None:
    results: list[dict[str, Any]] = body.get("results", [])
    if not results:
        return None
    first = results[0]
    return Place(name=first["formatted"], lat=first["lat"], lon=first["lon"])
