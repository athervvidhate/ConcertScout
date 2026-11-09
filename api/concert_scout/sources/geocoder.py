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
CITY_FIELDS = ("city", "state", "country")


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

    body = await _autocomplete(client, text)
    places = parse_places(body)
    # One city can come back as different records: "New York, NY" leads with one in Brooklyn.
    # The city's full name finds the record most people mean, so every spelling of a city lands
    # on one point, and so on one cached pool.
    if (city := _top_city(body)) and _full_name(city).casefold() != text.casefold():
        try:
            canonical = _top_city(await _autocomplete(client, _full_name(city)))
        except GeocoderError:
            canonical = None
        if canonical and _same_city(city, canonical):
            places[0] = _place(canonical)
    if places:
        await cache.write(redis, key, Places(places=places), CACHE_TTL)
    return places


async def _autocomplete(client: httpx.AsyncClient, text: str) -> dict[str, Any]:
    # `locality` covers cities, districts, counties and states, but not streets or venues.
    params = {"text": text, "type": "locality", "limit": CANDIDATES, "format": "json"}
    try:
        response = await client.get("/autocomplete", params=params)
        response.raise_for_status()
        body: dict[str, Any] = response.json()
        parse_places(body)
        return body
    except httpx.HTTPStatusError as exc:
        raise GeocoderError(f"status {exc.response.status_code}") from None
    except httpx.HTTPError as exc:
        raise GeocoderError(type(exc).__name__) from None
    except (KeyError, TypeError, ValueError) as exc:
        raise GeocoderError(f"unreadable response: {type(exc).__name__}") from None


def parse_places(body: dict[str, Any]) -> list[Place]:
    return [_place(record) for record in _ranked(body)]


def _ranked(body: dict[str, Any]) -> list[dict[str, Any]]:
    # Autocomplete orders by text, so a bare "Manchester" leads with New Hampshire. Geoapify's
    # importance puts the place most people mean first. The sort keeps ties in their order.
    results: list[dict[str, Any]] = sorted(
        body.get("results", []),
        key=lambda record: record.get("rank", {}).get("importance") or 0,
        reverse=True,
    )
    return [r for r in results if r.get("rank", {}).get("confidence", 1) >= MIN_CONFIDENCE]


def _place(record: dict[str, Any]) -> Place:
    state = record.get("result_type") == "state"
    country = str(record.get("country_code", "")).upper()
    return Place(
        name=record["formatted"],
        lat=record["lat"],
        lon=record["lon"],
        state_code=record.get("state_code") if state and country in {"US", "CA"} else None,
        country_code=country if state and country in {"US", "CA"} else None,
    )


def _top_city(body: dict[str, Any]) -> dict[str, Any] | None:
    ranked = _ranked(body)
    top = ranked[0] if ranked else None
    if top and top.get("result_type") == "city" and all(top.get(k) for k in CITY_FIELDS):
        return top
    return None


def _full_name(city: dict[str, Any]) -> str:
    return ", ".join(str(city[field]) for field in CITY_FIELDS)


def _same_city(first: dict[str, Any], second: dict[str, Any]) -> bool:
    return all(
        str(first.get(k, "")).casefold() == str(second.get(k, "")).casefold()
        for k in ("city", "state_code", "country_code")
    )
