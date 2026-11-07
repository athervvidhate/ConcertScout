import asyncio
import datetime as dt
import logging
from typing import Any

import httpx
from pygeohash import encode
from redis.asyncio import Redis

from concert_scout import limits
from concert_scout.models import Artist, Concert, Place, Price
from concert_scout.names import normalize
from concert_scout.sources import http

logger = logging.getLogger(__name__)

BASE_URL = "https://app.ticketmaster.com/discovery/v2"
PAGE_SIZE = 200
# Past this many results Ticketmaster answers 200 with no events, so a query is silently cut off.
MAX_RESULTS = 1000
RADIUS_MILES = 50
# About 5km, so Searches near each other share a pool without moving its 50-mile circle much.
POINT_PRECISION = 5
# Ticketmaster's words for having no classification.
NO_GENRE = {"other", "undefined"}


class TicketmasterError(Exception):
    """Ticketmaster failed. The message never holds the request URL, which carries the API key."""


def make_client(
    api_key: str, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    return http.make_client(BASE_URL, {"apikey": api_key}, transport)


def rounded_point(place: Place) -> str:
    return encode(place.lat, place.lon, precision=POINT_PRECISION)


async def find_concerts(
    client: httpx.AsyncClient, redis: Redis, point: str, start: dt.date, end: dt.date
) -> list[Concert]:
    return await _find(client, redis, _base_params(point), start, end)


async def find_artist_concerts(
    client: httpx.AsyncClient, redis: Redis, name: str, point: str | None
) -> list[Concert]:
    """An Artist's upcoming Concerts. `keyword` is loose, so code checks the Lineup."""
    concerts = await _find(client, redis, _base_params(point) | {"keyword": name})
    wanted = normalize(name)
    return [c for c in concerts if wanted in (normalize(a.name) for a in c.artists)]


def _base_params(point: str | None) -> dict[str, str | int]:
    params: dict[str, str | int] = {
        "segmentName": "Music",
        "size": PAGE_SIZE,
        "sort": "date,name,asc",
    }
    if point:
        params |= {"geoPoint": point, "radius": RADIUS_MILES, "unit": "miles"}
    return params


async def _find(
    client: httpx.AsyncClient,
    redis: Redis,
    params: dict[str, str | int],
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> list[Concert]:
    # The venue's local time, because `startDateTime` is UTC and would shift a late Concert a day.
    if start and end:
        params = params | {"localStartDateTime": f"{start}T00:00:00,{end}T23:59:59"}
    concerts, total = await _page(client, redis, params, 0)

    if total > MAX_RESULTS and start and end and start < end:
        middle = start + dt.timedelta(days=(end - start).days // 2)
        before, after = await asyncio.gather(
            _find(client, redis, params, start, middle),
            _find(client, redis, params, middle + dt.timedelta(days=1), end),
        )
        return before + after

    if total > MAX_RESULTS:
        logger.warning("Ticketmaster cut a query off at %d of %d", MAX_RESULTS, total)
    reachable = min(total, MAX_RESULTS)
    pages = range(1, (reachable + PAGE_SIZE - 1) // PAGE_SIZE)
    rest = await asyncio.gather(*(_page(client, redis, params, page) for page in pages))
    return concerts + [concert for page, _ in rest for concert in page]


async def _page(
    client: httpx.AsyncClient, redis: Redis, params: dict[str, str | int], page: int
) -> tuple[list[Concert], int]:
    await limits.ticketmaster_call(redis)
    try:
        response = await client.get("/events.json", params=params | {"page": page})
        response.raise_for_status()
        body = response.json()
        return parse_concerts(body), body["page"]["totalElements"]
    except httpx.HTTPStatusError as exc:
        raise TicketmasterError(f"status {exc.response.status_code}") from None
    except httpx.HTTPError as exc:
        raise TicketmasterError(type(exc).__name__) from None
    except (KeyError, TypeError, ValueError) as exc:
        raise TicketmasterError(f"unreadable response: {type(exc).__name__}") from None


def parse_concerts(body: dict[str, Any]) -> list[Concert]:
    records: list[dict[str, Any]] = body.get("_embedded", {}).get("events", [])
    return [
        parse_concert(record)
        for record in records
        if record["dates"].get("status", {}).get("code") != "cancelled"
    ]


def parse_concert(record: dict[str, Any]) -> Concert:
    embedded: dict[str, Any] = record.get("_embedded", {})
    venues: list[dict[str, Any]] = embedded.get("venues", [])
    venue = venues[0] if venues else {}
    start: dict[str, Any] = record["dates"].get("start", {})
    classifications: list[dict[str, Any]] = record.get("classifications", [])
    return Concert(
        id=record["id"],
        name=record["name"],
        url=record["url"],
        artists=[
            _parse_artist(a, classifications)
            for a in embedded.get("attractions", [])
            if "name" in a
        ],
        date=_parse_date(start),
        time=_parse_time(start),
        venue=venue.get("name"),
        city=venue.get("city", {}).get("name"),
        region=venue.get("state", {}).get("stateCode"),
        price=_parse_price(record.get("priceRanges", [])),
    )


def _parse_artist(
    attraction: dict[str, Any], event_classifications: list[dict[str, Any]]
) -> Artist:
    links: list[dict[str, Any]] = attraction.get("externalLinks", {}).get("musicbrainz", [])
    classifications = attraction.get("classifications") or event_classifications
    classification: dict[str, Any] = classifications[0] if classifications else {}
    return Artist(
        name=attraction["name"],
        mbid=links[0].get("id") if links else None,
        genre=_genre_name(classification.get("genre")),
        subgenre=_genre_name(classification.get("subGenre")),
    )


def _genre_name(genre: dict[str, Any] | None) -> str | None:
    name = genre.get("name") if genre else None
    return name if name and name.casefold() not in NO_GENRE else None


def _parse_date(start: dict[str, Any]) -> dt.date | None:
    if start.get("dateTBD") or start.get("dateTBA") or "localDate" not in start:
        return None
    return dt.date.fromisoformat(start["localDate"])


def _parse_time(start: dict[str, Any]) -> dt.time | None:
    if start.get("timeTBA") or start.get("noSpecificTime") or "localTime" not in start:
        return None
    return dt.time.fromisoformat(start["localTime"])


def _parse_price(ranges: list[dict[str, Any]]) -> Price | None:
    if not ranges:
        return None
    first = ranges[0]
    # Ticketmaster reports 0-0 for listings with no known price, including sold-out ones.
    if not first.get("max") or "min" not in first or "currency" not in first:
        return None
    return Price(min=first["min"], max=first["max"], currency=first["currency"])
