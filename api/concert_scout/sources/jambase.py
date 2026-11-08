"""JamBase background collection and read-only local catalog. No HTTP on the Search path."""

import asyncio
import datetime as dt
import logging
import math
import secrets
import time
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError

from concert_scout import cache, clock
from concert_scout.models import Artist, Concert, Place
from concert_scout.names import normalize
from concert_scout.sources.http import USER_AGENT

logger = logging.getLogger(__name__)
BASE_URL = "https://api.data.jambase.com"
# A 30-day California catalog took 25 pages on November 7, 2026. Refreshing every second
# day keeps a month under MONTHLY_LIMIT; the cache outlives one failed run.
CACHE_AGE = dt.timedelta(hours=96)
REFRESH_AFTER = dt.timedelta(hours=44)
REQUEST_LIMIT = 40
MONTHLY_LIMIT = 750  # Leave room below the Developer plan's 1,000 included calls.
MIN_REMAINING = 25
LOCK_SECONDS = 120
PAGE_SIZE = 100


class JamBaseError(Exception):
    """Contains only safe codes, never a request, header or response body."""


class Listing(BaseModel):
    concert: Concert
    latitude: float | None
    longitude: float | None
    country: str | None


class Catalog(BaseModel):
    refreshed_at: dt.datetime
    first: dt.date
    last: dt.date
    listings: list[Listing]


class Refreshed(BaseModel):
    region: str
    concerts: int = 0
    requests: int = 0
    seconds: float = 0
    error: str | None = None


def make_client(key: str, transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {key}", "User-Agent": USER_AGENT},
        timeout=10,
        transport=transport,
    )


def catalog_key(region: str) -> str:
    return f"jambase:catalog:{region}"


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
    country: dict[str, Any] = address.get("addressCountry") or {}
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
            image=_image(lead) or _image(record),
        ),
        latitude=geo.get("latitude"),
        longitude=geo.get("longitude"),
        country=country.get("identifier"),
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


async def refresh(
    client: httpx.AsyncClient,
    redis: Redis,
    regions: Sequence[str],
    days: int,
    now: dt.datetime,
) -> list[Refreshed]:
    try:
        async with asyncio.timeout(90):
            return await _refresh_locked(client, redis, regions, days, now)
    except TimeoutError:
        return [Refreshed(region="JamBase", error="refresh timed out")]


async def _release(redis: Redis, token: str) -> None:
    try:
        async with redis.pipeline() as pipe:
            await pipe.watch("jambase:refresh-lock")
            if await pipe.get("jambase:refresh-lock") == token.encode():
                pipe.multi()
                pipe.delete("jambase:refresh-lock")
                await pipe.execute()
    except RedisError:
        pass


async def _refresh_locked(
    client: httpx.AsyncClient,
    redis: Redis,
    regions: Sequence[str],
    days: int,
    now: dt.datetime,
) -> list[Refreshed]:
    """One shared writer, quota checked before work, complete generations published atomically."""
    results: list[Refreshed] = []
    token = secrets.token_hex(16)
    try:
        # Fail closed if Redis cannot enforce single-writer or publish a catalog.
        if not await redis.set("jambase:refresh-lock", token, nx=True, ex=LOCK_SECONDS):
            return [Refreshed(region="JamBase", error="refresh already running")]
    except RedisError:
        return [Refreshed(region="JamBase", error="cache unavailable")]
    requests = 0
    try:
        quota = await _get(client, "/v3/quota", {})
        used = int(quota["usedCalls"])
        allowance = min(int(quota["remainingCalls"]), MONTHLY_LIMIT - used)
        if allowance <= MIN_REMAINING:
            return [Refreshed(region="JamBase", error="included quota reserved; no overage")]
        for region in regions:
            began = time.perf_counter()
            result = Refreshed(region=region)
            results.append(result)
            current = await cache.read(redis, catalog_key(region), Catalog)
            if current and now - current.refreshed_at < REFRESH_AFTER:
                result.concerts = len(current.listings)
                continue
            try:
                if len(region) != 5 or region[:3] != "US-":
                    raise JamBaseError("unsupported region")
                first = now.date() - dt.timedelta(days=1)
                last = now.date() + dt.timedelta(days=min(max(days, 1), 180))
                rows: dict[str, Listing] = {}
                seen: set[str] = set()
                total = 0
                page = 1
                while True:
                    if requests >= REQUEST_LIMIT or allowance - requests <= MIN_REMAINING:
                        raise JamBaseError("refresh budget exhausted")
                    params: dict[str, str | int] = {
                        "geoCountryIso2": "US",
                        "geoStateIso": region,
                        "eventDateFrom": str(first),
                        "eventDateTo": str(last + dt.timedelta(days=1)),
                        "perPage": PAGE_SIZE,
                        "page": page,
                    }
                    started = time.perf_counter()
                    body = await _get(client, "/v3/events", params)
                    requests += 1
                    result.requests += 1
                    if body.get("success") is not True:
                        raise JamBaseError("unsuccessful response")
                    total = int(body["pagination"]["totalItems"])
                    pages = int(body["pagination"]["totalPages"])
                    if pages > REQUEST_LIMIT - requests + page:
                        raise JamBaseError("catalog exceeds refresh budget")
                    for record in body["events"]:
                        seen.add(record["identifier"])
                        if record.get("eventStatus") in {"cancelled", "postponed"}:
                            continue
                        listing = parse_listing(record)
                        rows[listing.concert.id] = listing
                    if page >= pages:
                        break
                    # Developer steady rate is one request/second, shared by this writer.
                    await asyncio.sleep(max(0, 1 - (time.perf_counter() - started)))
                    page += 1
                if len(seen) != total:
                    raise JamBaseError("incomplete catalog")
                catalog = Catalog(
                    refreshed_at=now, first=first, last=last, listings=list(rows.values())
                )
                await redis.set(catalog_key(region), catalog.model_dump_json(), ex=CACHE_AGE)
                result.concerts = len(rows)
            except (JamBaseError, KeyError, ValueError, TypeError, RedisError) as exc:
                result.error = str(exc) if isinstance(exc, JamBaseError) else type(exc).__name__
            result.seconds = round(time.perf_counter() - began, 3)
    except (JamBaseError, KeyError, ValueError, TypeError) as exc:
        results.append(Refreshed(region="JamBase", error=type(exc).__name__))
    finally:
        # The lock lives longer than the bounded source job; it also expires after a crash.
        await _release(redis, token)
    return results


def _near(listing: Listing, place: Place) -> bool:
    if place.state_code and place.country_code:
        return listing.country == place.country_code and listing.concert.region == place.state_code
    if listing.latitude is None or listing.longitude is None:
        return False
    latitude, longitude = math.radians(place.lat), math.radians(place.lon)
    other_lat, other_lon = math.radians(listing.latitude), math.radians(listing.longitude)
    value = (
        math.sin((other_lat - latitude) / 2) ** 2
        + math.cos(latitude) * math.cos(other_lat) * math.sin((other_lon - longitude) / 2) ** 2
    )
    miles = 3958.8 * 2 * math.asin(min(1, math.sqrt(value)))
    return miles <= (place.radius_miles or 50)


async def cached_concerts(
    redis: Redis,
    regions: Sequence[str],
    place: Place | None,
    artists: Sequence[str],
    start: dt.date | None,
    end: dt.date | None,
    now: dt.datetime,
) -> list[Concert]:
    keys = [
        catalog_key(r)
        for r in regions
        if not place or not place.country_code or r.startswith(place.country_code + "-")
    ]
    snapshots = await cache.read_many(redis, keys, Catalog)
    wanted = {normalize(a) for a in artists}
    concerts: dict[str, Concert] = {}
    for snapshot in snapshots.values():
        if now - snapshot.refreshed_at > CACHE_AGE:
            continue
        for listing in snapshot.listings:
            concert = listing.concert
            today = clock.date_at(now, concert.time_zone)
            if not concert.date or concert.date < max(start or today, today):
                continue
            if end and concert.date > end:
                continue
            if place and not _near(listing, place):
                continue
            if not place and not any(normalize(a.name) in wanted for a in concert.artists):
                continue
            concerts[concert.id] = concert
    return list(concerts.values())
