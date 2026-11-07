import datetime as dt
from typing import Any

import httpx
from redis.asyncio import Redis

from concert_scout import cache
from concert_scout.aliases import place_name
from concert_scout.models import Place, Places
from concert_scout.sources import http

BASE_URL = "https://api.geoapify.com/v1/geocode"
CACHE_TTL = dt.timedelta(days=30)
# Below this, Geoapify is guessing from part of the text: "Southern California" scores 0 as
# "Southern Concord". Saying we could not find a place beats searching the wrong one.
MIN_CONFIDENCE = 0.8
# Enough that a bigger place with the same name is among them.
CANDIDATES = 5


class GeocoderError(Exception):
    """Geoapify failed. The message never holds the request URL, which carries the API key."""


def make_client(
    api_key: str, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    return http.make_client(BASE_URL, {"apiKey": api_key}, transport)


async def geocode(client: httpx.AsyncClient, redis: Redis, text: str) -> Place | None:
    places = await find_places(client, redis, text)
    return places[0] if places else None


async def find_places(client: httpx.AsyncClient, redis: Redis, text: str) -> list[Place]:
    text = place_name(text)
    key = f"geocode:v4:{' '.join(text.casefold().split())}"
    if cached := await cache.read(redis, key, Places):
        return cached.places

    # `locality` covers cities, districts, counties and states, but not streets or venues.
    params = {"text": text, "type": "locality", "limit": CANDIDATES, "format": "json"}
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
    # Autocomplete orders by text, so a bare "Manchester" leads with New Hampshire. Geoapify's
    # importance puts the place most people mean first. The sort keeps ties in their order.
    results: list[dict[str, Any]] = sorted(
        body.get("results", []),
        key=lambda record: record.get("rank", {}).get("importance") or 0,
        reverse=True,
    )
    places: list[Place] = []
    for record in results:
        if record.get("rank", {}).get("confidence", 1) < MIN_CONFIDENCE:
            continue
        state = record.get("result_type") == "state"
        country = str(record.get("country_code", "")).upper()
        places.append(
            Place(
                name=record["formatted"],
                lat=record["lat"],
                lon=record["lon"],
                state_code=record.get("state_code") if state and country in {"US", "CA"} else None,
                country_code=country if state and country in {"US", "CA"} else None,
            )
        )
    return places
