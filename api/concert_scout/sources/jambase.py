"""JamBase Data API: HTTP and parsing only. Only the background sync calls it."""

import datetime as dt
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel

from concert_scout import clock
from concert_scout.models import Artist, Concert
from concert_scout.sources.http import USER_AGENT

BASE_URL = "https://api.data.jambase.com"
PAGE_SIZE = 100
# Statuses that leave nothing to attend at the listed place and date.
GONE = frozenset({"cancelled", "postponed", "movedOnline"})


class JamBaseError(Exception):
    """Contains only safe codes, never a request, header or response body."""


class Listing(BaseModel):
    concert: Concert
    latitude: float | None
    longitude: float | None


class Page(BaseModel):
    listings: list[Listing]
    # Events that should leave the catalog: gone by status, or removal rows.
    removed: list[str]
    total: int
    pages: int


class Quota(BaseModel):
    used: int
    remaining: int


def make_client(key: str, transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {key}", "User-Agent": USER_AGENT},
        timeout=15,
        transport=transport,
    )


def _image(record: dict[str, Any]) -> str | None:
    image = record.get("image")
    if not isinstance(image, str):
        return None
    url = urlsplit(image)
    if url.scheme != "https" or url.hostname != "www.jambase.com":
        return None
    if not url.path.startswith("/wp-content/uploads/") or "default" in url.path.lower():
        return None
    return image


def parse_listing(record: dict[str, Any]) -> Listing:
    location: dict[str, Any] = record.get("location") or {}
    address: dict[str, Any] = location.get("address") or {}
    region: dict[str, Any] = address.get("addressRegion") or {}
    geo: dict[str, Any] = location.get("geo") or {}
    performers: list[dict[str, Any]] = record.get("performer") or []
    lead = performers[0] if performers else {}
    start = record.get("startDate") or ""
    date = dt.date.fromisoformat(start[:10]) if start else None
    parsed = dt.datetime.fromisoformat(start) if "T" in start else None
    # A date-only or midnight placeholder is not a known performance time.
    known_time = (
        parsed.time().replace(tzinfo=None) if parsed and parsed.time() != dt.time() else None
    )
    zone = address.get("x-timezone")
    # A festival's name says what it is, and its own poster beats its first performer's photo.
    festival = record.get("@type") == "Festival"
    image = (_image(record) or _image(lead)) if festival else (_image(lead) or _image(record))
    return Listing(
        concert=Concert(
            id=record["identifier"],
            name=record["name"],
            url=record["url"],
            source="jambase",
            artists=[
                Artist(
                    name=p["name"],
                    source_id=p.get("identifier"),
                    genre=(p.get("genre") or [None])[0],
                )
                for p in performers
            ],
            date=date,
            time=known_time,
            time_zone=zone if clock.known_zone(zone) else None,
            venue=location.get("name"),
            city=address.get("addressLocality"),
            region=region.get("alternateName"),
            image=image,
            festival=festival,
        ),
        latitude=geo.get("latitude"),
        longitude=geo.get("longitude"),
    )


def parse_page(body: dict[str, Any]) -> Page:
    if body.get("success") is not True:
        raise JamBaseError("unsuccessful response")
    listings: list[Listing] = []
    removed: list[str] = []
    for record in body["events"]:
        if record.get("deletionStatus") or record.get("eventStatus") in GONE:
            removed.append(record["identifier"])
        else:
            listings.append(parse_listing(record))
    pagination = body["pagination"]
    return Page(
        listings=listings,
        removed=removed,
        total=int(pagination["totalItems"]),
        pages=int(pagination["totalPages"]),
    )


async def _get(
    client: httpx.AsyncClient, path: str, params: dict[str, str | int]
) -> dict[str, Any]:
    try:
        response = await client.get(path, params=params)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        raise JamBaseError(f"HTTP {exc.response.status_code}") from None
    except (httpx.HTTPError, ValueError) as exc:
        raise JamBaseError(type(exc).__name__) from None


async def quota(client: httpx.AsyncClient) -> Quota:
    body = await _get(client, "/v3/quota", {})
    try:
        return Quota(used=int(body["usedCalls"]), remaining=int(body["remainingCalls"]))
    except (KeyError, TypeError, ValueError):
        raise JamBaseError("unreadable quota") from None


async def events(client: httpx.AsyncClient, params: dict[str, str | int], page: int) -> Page:
    body = await _get(client, "/v3/events", {**params, "perPage": PAGE_SIZE, "page": page})
    try:
        return parse_page(body)
    except (KeyError, TypeError, ValueError):
        raise JamBaseError("unreadable events") from None
