import datetime as dt
from typing import Any

import httpx
from httpx_retries import Retry, RetryTransport

from concert_scout.models import Concert, Price

BASE_URL = "https://app.ticketmaster.com/discovery/v2"
USER_AGENT = "ConcertScout (+https://github.com/athervvidhate/ConcertScoutAI)"
PAGE_SIZE = 50


class TicketmasterError(Exception):
    """Ticketmaster failed. The message never holds the request URL, which carries the API key."""


def make_client(
    api_key: str, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=BASE_URL,
        params={"apikey": api_key},
        headers={"User-Agent": USER_AGENT},
        timeout=10.0,
        transport=RetryTransport(transport, retry=Retry(total=2, backoff_factor=0.5)),
    )


async def find_concerts(client: httpx.AsyncClient, city: str) -> list[Concert]:
    params = {"city": city, "segmentName": "Music", "size": PAGE_SIZE, "sort": "date,asc"}
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
