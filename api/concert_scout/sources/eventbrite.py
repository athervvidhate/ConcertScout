"""Bounded organizer API adapter. Not enabled in production Search or any scheduled job.

An Eventbrite title is not a performer list: afterparties often name absent Artists.
"""

import datetime as dt
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel

from concert_scout import clock
from concert_scout.models import Concert, Price
from concert_scout.sources.http import USER_AGENT

BASE_URL = "https://www.eventbriteapi.com/v3/"
PAGE_LIMIT = 5


class EventbriteError(Exception):
    """Safe error codes only, without response bodies, headers or account details."""


class Listing(BaseModel):
    source: Literal["eventbrite"] = "eventbrite"
    concert: Concert
    organizer_id: str
    latitude: float | None
    longitude: float | None
    country: str | None
    ends_at: dt.datetime
    sold_out: bool | None
    # These are event photos, never asserted to be Artist portraits.
    image_kind: str = "event"


def make_client(token: str, transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT},
        timeout=10,
        transport=transport,
    )


def parse_listing(record: dict[str, Any], now: dt.datetime) -> Listing | None:
    """Only public, physical Music listings whose end is still ahead; missing facts stay absent."""
    if (
        record.get("status") != "live"
        or record.get("listed") is not True
        or record.get("shareable") is not True
        or record.get("online_event") is not False
        or record.get("is_series_parent") is True
        or record.get("category_id") != "103"
        or record.get("hide_start_date") is True
    ):
        return None
    end: dict[str, Any] = record.get("end") or {}
    if not end.get("utc"):
        return None
    ends_at = dt.datetime.fromisoformat(end["utc"])
    if ends_at.tzinfo is None or ends_at <= now:
        return None
    start: dict[str, Any] = record.get("start") or {}
    if not start.get("local"):
        return None
    local = dt.datetime.fromisoformat(start["local"])
    zone = start.get("timezone")
    venue: dict[str, Any] = record.get("venue") or {}
    address: dict[str, Any] = venue.get("address") or {}
    tickets: dict[str, Any] = record.get("ticket_availability") or {}
    low: Any = tickets.get("minimum_ticket_price")
    high: Any = tickets.get("maximum_ticket_price")
    price = None
    if low and high and low.get("currency") == high.get("currency"):
        price = Price(
            min=float(low["major_value"]), max=float(high["major_value"]), currency=low["currency"]
        )
    logo: dict[str, Any] = record.get("logo") or {}
    image: str | None = logo.get("url")
    if image and urlsplit(image).scheme != "https":
        image = None
    return Listing(
        concert=Concert(
            id=f"eventbrite:{record['id']}",
            name=record["name"]["text"],
            url=record["url"],
            artists=[],
            date=local.date(),
            time=local.time(),
            time_zone=zone if clock.known_zone(zone) else None,
            venue=venue.get("name"),
            city=address.get("city"),
            region=address.get("region"),
            image=image,
            price=price,
        ),
        organizer_id=record["organizer_id"],
        latitude=venue.get("latitude"),
        longitude=venue.get("longitude"),
        country=address.get("country"),
        ends_at=ends_at,
        sold_out=tickets.get("is_sold_out"),
    )


async def organizer_listings(
    client: httpx.AsyncClient,
    organizer_id: str,
    now: dt.datetime,
) -> list[Listing]:
    """Read one explicitly chosen organizer; reject partial pagination, never silently truncate.

    No broad search, retries, account lookup, ticket purchase or private-event endpoint.
    """
    if not organizer_id.isascii() or not organizer_id.isdigit():
        raise EventbriteError("invalid organizer ID")
    listings: dict[str, Listing] = {}
    seen: set[str] = set()
    for page in range(1, PAGE_LIMIT + 1):
        try:
            response = await client.get(
                f"organizers/{organizer_id}/events/",
                params={
                    "status": "live",
                    "order_by": "start_asc",
                    "page": page,
                    "expand": "venue,category,format,ticket_availability",
                },
            )
            response.raise_for_status()
            body = response.json()
            pagination = body["pagination"]
            for record in body["events"]:
                if record.get("organizer_id") != organizer_id:
                    raise EventbriteError("organizer mismatch")
                seen.add(record["id"])
                if listing := parse_listing(record, now):
                    listings[listing.concert.id] = listing
            if not pagination["has_more_items"]:
                if len(seen) != int(pagination["object_count"]):
                    raise EventbriteError("incomplete organizer response")
                return list(listings.values())
        except httpx.HTTPStatusError as exc:
            raise EventbriteError(f"HTTP {exc.response.status_code}") from None
        except httpx.HTTPError as exc:
            raise EventbriteError(type(exc).__name__) from None
        except (KeyError, ValueError, TypeError):
            raise EventbriteError("invalid organizer response") from None
    raise EventbriteError("organizer page budget exceeded")
