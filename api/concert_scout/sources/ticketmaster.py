import asyncio
import datetime as dt
import logging
import re
from typing import Any

import httpx
from pygeohash import encode
from redis.asyncio import Redis

from concert_scout import clock, limits
from concert_scout.models import Artist, Concert, Place, Presale, Price
from concert_scout.names import normalize
from concert_scout.sources import http

logger = logging.getLogger(__name__)

BASE_URL = "https://app.ticketmaster.com/discovery/v2"
PAGE_SIZE = 200
# Past this many results Ticketmaster answers 200 with no events, so a query is silently cut off.
MAX_RESULTS = 1000
RADIUS_MILES = 50
# Ticketmaster fills an unknown sale date with a date from long ago, such as 1900-01-01.
FIRST_REAL_SALE = dt.datetime(2000, 1, 1, tzinfo=dt.UTC)
NOT_A_PRESALE = re.compile(r"vip|onsale", re.IGNORECASE)
# About 5km, so Searches near each other share a pool without moving its 50-mile circle much.
POINT_PRECISION = 5
# Ticketmaster's words for having no classification.
NO_GENRE = {"other", "undefined"}
IMAGE_RATIO = "16_9"
IMAGE_MIN_WIDTH = 640


class TicketmasterError(Exception):
    """Ticketmaster failed. The message never holds the request URL, which carries the API key."""


def make_client(
    api_key: str, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    return http.make_client(BASE_URL, {"apikey": api_key}, transport)


def rounded_point(place: Place) -> str:
    return encode(place.lat, place.lon, precision=POINT_PRECISION)


async def find_concerts(
    client: httpx.AsyncClient,
    redis: Redis,
    point: str | None,
    start: dt.date,
    end: dt.date,
    *,
    state: tuple[str, str] | None = None,
    radius: int = RADIUS_MILES,
) -> list[Concert]:
    return await _find(client, redis, _base_params(point, state, radius), start, end)


async def find_artist_concerts(
    client: httpx.AsyncClient,
    redis: Redis,
    name: str,
    point: str | None,
    *,
    state: tuple[str, str] | None = None,
    radius: int = RADIUS_MILES,
) -> list[Concert]:
    """An Artist's upcoming Concerts. `keyword` is loose, so code checks the Lineup."""
    params = _base_params(point, state, radius) | {"keyword": name}
    concerts = await _find(client, redis, params)
    wanted = normalize(name)
    return [c for c in concerts if wanted in (normalize(a.name) for a in c.artists)]


def _base_params(
    point: str | None, state: tuple[str, str] | None, radius: int
) -> dict[str, str | int]:
    params: dict[str, str | int] = {
        "segmentName": "Music",
        "size": PAGE_SIZE,
        "sort": "date,name,asc",
    }
    if state:
        params |= {"countryCode": state[0], "stateCode": state[1]}
    elif point:
        params |= {"geoPoint": point, "radius": radius, "unit": "miles"}
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


async def find_keyword(
    client: httpx.AsyncClient, redis: Redis, keyword: str, start: dt.date, end: dt.date, size: int
) -> list[Concert]:
    """The soonest music matching a word anywhere, in one call, however many there are."""
    params: dict[str, str | int] = {
        "keyword": keyword,
        "classificationName": "music",
        "sort": "date,asc",
        "size": size,
        "localStartDateTime": f"{start}T00:00:00,{end}T23:59:59",
    }
    concerts, _ = await _page(client, redis, params, 0)
    return concerts


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
    attractions: list[dict[str, Any]] = embedded.get("attractions", [])
    lead: dict[str, Any] = attractions[0] if attractions else {}
    general_sale, presales = _parse_sales(record.get("sales", {}))
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
        time_zone=venue.get("timezone") if clock.known_zone(venue.get("timezone")) else None,
        venue=venue.get("name"),
        city=venue.get("city", {}).get("name"),
        region=venue.get("state", {}).get("stateCode"),
        price=_parse_price(record.get("priceRanges", [])),
        image=_image(lead.get("images", [])) or _image(record.get("images", [])),
        general_sale=general_sale,
        presales=presales,
    )


def _parse_sales(sales: dict[str, Any]) -> tuple[dt.datetime | None, list[Presale]]:
    """The general sale and the presales open to anyone with a code.

    With no general sale date and none announced, nothing says the presales still matter.
    """
    public: dict[str, Any] = sales.get("public", {})
    general = _parse_moment(public.get("startDateTime"))
    if general and general < FIRST_REAL_SALE:
        general = None
    if not general and not public.get("startTBA"):
        return None, []
    return general, [p for r in sales.get("presales", []) if (p := _parse_presale(r))]


def _parse_presale(record: dict[str, Any]) -> Presale | None:
    name: str = record.get("name") or ""
    start = _parse_moment(record.get("startDateTime"))
    end = _parse_moment(record.get("endDateTime"))
    if not (name and start and end) or NOT_A_PRESALE.search(name):
        return None
    name = name.title() if name.isupper() else name
    return Presale(
        name=name if "presale" in name.lower() else f"{name} presale", start=start, end=end
    )


def _parse_moment(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value)
    except ValueError:
        return None


def _image(images: list[dict[str, Any]]) -> str | None:
    """The smallest real photo wide enough for a Ticket. `fallback` marks a generic placeholder."""
    usable = [
        image
        for image in images
        if image.get("url")
        and image.get("ratio") == IMAGE_RATIO
        and not image.get("fallback")
        and (image.get("width") or 0) >= IMAGE_MIN_WIDTH
    ]
    return min(usable, key=lambda image: image["width"])["url"] if usable else None


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
