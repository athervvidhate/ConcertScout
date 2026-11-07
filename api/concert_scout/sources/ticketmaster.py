import datetime as dt
from typing import Any

import httpx
from pygeohash import encode

from concert_scout.models import Concert, Place, Price
from concert_scout.sources import http

BASE_URL = "https://app.ticketmaster.com/discovery/v2"
PAGE_SIZE = 50
RADIUS_MILES = 50


class TicketmasterError(Exception):
    """Ticketmaster failed. The message never holds the request URL, which carries the API key."""


def make_client(
    api_key: str, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    return http.make_client(BASE_URL, {"apikey": api_key}, transport)


async def find_concerts(
    client: httpx.AsyncClient,
    place: Place,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> list[Concert]:
    params: dict[str, str | int] = {
        "geoPoint": encode(place.lat, place.lon, precision=9),
        "radius": RADIUS_MILES,
        "unit": "miles",
        "segmentName": "Music",
        "size": PAGE_SIZE,
        "sort": "date,asc",
    }
    # The venue's local time, because `startDateTime` is UTC and would shift a late Concert a day.
    if start or end:
        first = f"{start}T00:00:00" if start else "*"
        last = f"{end}T23:59:59" if end else "*"
        params["localStartDateTime"] = f"{first},{last}"
    try:
        response = await client.get("/events.json", params=params)
        response.raise_for_status()
        return parse_concerts(response.json())
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
    return Concert(
        id=record["id"],
        name=record["name"],
        url=record["url"],
        artists=[a["name"] for a in embedded.get("attractions", []) if "name" in a],
        date=_parse_date(start),
        time=_parse_time(start),
        venue=venue.get("name"),
        city=venue.get("city", {}).get("name"),
        region=venue.get("state", {}).get("stateCode"),
        price=_parse_price(record.get("priceRanges", [])),
    )


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
