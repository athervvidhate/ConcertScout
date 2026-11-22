"""Polite `schema.org/MusicEvent` JSON-LD calendar fetcher and extractor.

Only called by the authenticated `/sync-underground` job against curated venue URLs.
Never invents missing facts; extracted performer names stay outside `Concert.artists` until
MusicBrainz confirms them in `underground.py`.
"""

import datetime as dt
import hashlib
import html
import json
import logging
from html.parser import HTMLParser
from typing import Any, cast
from urllib.parse import urljoin, urlsplit

import httpx
from pydantic import BaseModel

from concert_scout import clock
from concert_scout.models import Concert, Price
from concert_scout.names import normalize
from concert_scout.sources import http
from concert_scout.underground_registry import UndergroundVenue

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 2_000_000
TIMEOUT_SECONDS = 10.0

_DROPPED_STATUSES = frozenset(
    {
        "eventcancelled",
        "eventcanceled",
        "eventpostponed",
        "eventmovedonline",
        "cancelled",
        "canceled",
        "postponed",
        "movedonline",
    }
)
_SOLD_OUT_AVAILABILITY = frozenset({"soldout"})
_AVAILABLE_AVAILABILITY = frozenset(
    {"instock", "preorder", "presale", "limitedavailability", "onlineonly"}
)


class JsonLdError(Exception):
    """Safe error codes only, never raw response bodies, headers or secrets."""


class ExtractedEvent(BaseModel):
    concert: Concert
    performer_names: list[str] = []
    latitude: float
    longitude: float


def make_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    """Polite client via `sources.http.make_client`: app User-Agent, strict timeout, no retries."""
    return http.make_client(
        "",
        {},
        transport,
        headers={"Accept": "text/html, application/ld+json;q=0.9"},
        timeout=TIMEOUT_SECONDS,
        retries=0,
    )


class _JsonLdScriptParser(HTMLParser):
    """Collects contents of `<script type="application/ld+json">` tags without extra deps."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._in_jsonld = False
        self._chunks: list[str] = []
        self.blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        media = next((v for k, v in attrs if k.lower() == "type" and v), "")
        if media.split(";", 1)[0].strip().lower() == "application/ld+json":
            self._in_jsonld = True
            self._chunks = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._in_jsonld:
            self._in_jsonld = False
            block = "".join(self._chunks).strip()
            if block:
                self.blocks.append(block)
            self._chunks = []

    def handle_data(self, data: str) -> None:
        if self._in_jsonld:
            self._chunks.append(data)


def _schema_token(value: str) -> str:
    """Strip `https://schema.org/` or `schema:` prefix and fold case."""
    cleaned = value.strip().rstrip("/")
    if "/" in cleaned:
        cleaned = cleaned.rsplit("/", 1)[-1]
    if ":" in cleaned:
        cleaned = cleaned.rsplit(":", 1)[-1]
    return cleaned.lower()


def _as_dict(value: Any) -> dict[str, Any] | None:
    return cast(dict[str, Any], value) if isinstance(value, dict) else None


def _as_list(value: Any) -> list[Any] | None:
    return cast(list[Any], value) if isinstance(value, list) else None


def _is_music_event(node: dict[str, Any]) -> bool:
    raw = node.get("@type")
    if isinstance(raw, str):
        return _schema_token(raw) == "musicevent"
    if (types := _as_list(raw)) is not None:
        return any(isinstance(item, str) and _schema_token(item) == "musicevent" for item in types)
    return False


def _collect_music_events(payload: Any, found: list[dict[str, Any]]) -> None:
    if (items := _as_list(payload)) is not None:
        for item in items:
            _collect_music_events(item, found)
        return
    node = _as_dict(payload)
    if node is None:
        return
    if _is_music_event(node):
        found.append(node)
    if (graph := _as_list(node.get("@graph"))) is not None:
        for item in graph:
            _collect_music_events(item, found)


def _extract_blocks(document: str) -> list[str]:
    stripped = document.lstrip()
    if stripped.startswith(("{", "[")):
        return [stripped]
    parser = _JsonLdScriptParser()
    parser.feed(document)
    parser.close()
    return parser.blocks


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(html.unescape(value).split()).strip()
    return text or None


def _resolve_https(raw: Any, base_url: str) -> str | None:
    if not isinstance(raw, str):
        return None
    candidate = raw.strip()
    if not candidate:
        return None
    resolved = urljoin(base_url, candidate)
    parsed = urlsplit(resolved)
    if parsed.scheme != "https" or not parsed.netloc:
        return None
    return resolved


def _parse_start(raw: Any, time_zone: str) -> tuple[dt.date, dt.time | None] | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    zone = clock.known_zone(time_zone)
    try:
        if "T" not in text and " " not in text:
            return dt.date.fromisoformat(text[:10]), None
        normalized = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is not None and zone is not None:
        parsed = parsed.astimezone(zone)
    return parsed.date(), parsed.time().replace(tzinfo=None)


def _dropped_status(record: dict[str, Any]) -> bool:
    raw = record.get("eventStatus")
    statuses: list[Any]
    if isinstance(raw, str):
        statuses = [raw]
    elif (listed := _as_list(raw)) is not None:
        statuses = listed
    else:
        statuses = []
    return any(isinstance(s, str) and _schema_token(s) in _DROPPED_STATUSES for s in statuses)


def _parse_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        amount = float(value)
        return amount if amount >= 0 else None
    if isinstance(value, str):
        cleaned = value.strip().lstrip("$")
        try:
            amount = float(cleaned)
        except ValueError:
            return None
        return amount if amount >= 0 else None
    return None


def _parse_offers(raw_offers: Any, base_url: str) -> tuple[Price | None, bool | None, str | None]:
    offers: list[dict[str, Any]] = []
    if (single := _as_dict(raw_offers)) is not None:
        offers = [single]
    elif (listed := _as_list(raw_offers)) is not None:
        offers = [d for item in listed if (d := _as_dict(item)) is not None]
    if not offers:
        return None, None, None

    prices_by_currency: dict[str, list[float]] = {}
    saw_sold_out = False
    saw_available = False
    offer_url: str | None = None

    for offer in offers:
        if offer_url is None:
            offer_url = _resolve_https(offer.get("url"), base_url)
        availability = offer.get("availability")
        if isinstance(availability, str):
            token = _schema_token(availability)
            if token in _SOLD_OUT_AVAILABILITY:
                saw_sold_out = True
            elif token in _AVAILABLE_AVAILABILITY:
                saw_available = True
        currency = offer.get("priceCurrency")
        if isinstance(currency, str) and currency.strip():
            code = currency.strip().upper()
            for field in ("price", "lowPrice", "highPrice"):
                amount = _parse_number(offer.get(field))
                if amount is not None:
                    prices_by_currency.setdefault(code, []).append(amount)

    price: Price | None = None
    if prices_by_currency:
        currency, amounts = next(iter(prices_by_currency.items()))
        price = Price(min=min(amounts), max=max(amounts), currency=currency)

    sold_out: bool | None = None
    if saw_sold_out and not saw_available:
        sold_out = True
    elif saw_available:
        sold_out = False

    return price, sold_out, offer_url


def _parse_image(raw_image: Any, base_url: str) -> str | None:
    if isinstance(raw_image, str):
        return _resolve_https(raw_image, base_url)
    if (obj := _as_dict(raw_image)) is not None:
        return _resolve_https(obj.get("url") or obj.get("contentUrl"), base_url)
    if (listed := _as_list(raw_image)) is not None:
        for item in listed:
            if resolved := _parse_image(item, base_url):
                return resolved
    return None


def _parse_performers(record: dict[str, Any]) -> list[str]:
    raw = record.get("performer")
    if raw is None:
        raw = record.get("performers")
    items: list[Any]
    if (listed := _as_list(raw)) is not None:
        items = listed
    elif raw is not None:
        items = [raw]
    else:
        items = []
    names: list[str] = []
    seen: set[str] = set()
    for item in items:
        candidate = _clean_text(item) if isinstance(item, str) else None
        if (obj := _as_dict(item)) is not None:
            candidate = _clean_text(obj.get("name"))
        if not candidate:
            continue
        key = normalize(candidate)
        if key and key not in seen:
            seen.add(key)
            names.append(candidate)
    return names


def _event_id(
    venue: UndergroundVenue,
    date: dt.date,
    time: dt.time | None,
    url: str,
    name: str,
) -> str:
    anchor = url if url != venue.calendar_url else normalize(name)
    stamp = f"{date.isoformat()}T{time.isoformat()}" if time else date.isoformat()
    digest = hashlib.sha256(f"{venue.slug}|{stamp}|{anchor}".encode()).hexdigest()[:16]
    return f"venue:{venue.slug}:{digest}"


def parse_event(
    record: dict[str, Any], venue: UndergroundVenue, now: dt.datetime
) -> ExtractedEvent | None:
    """Parse one `schema.org/MusicEvent` node. Missing facts stay None; invalid records drop."""
    if _dropped_status(record):
        return None
    name = _clean_text(record.get("name"))
    if not name:
        return None
    start = _parse_start(record.get("startDate"), venue.time_zone)
    if start is None:
        return None
    date, local_time = start
    if date < clock.date_at(now, venue.time_zone):
        return None

    price, sold_out, offer_url = _parse_offers(record.get("offers"), venue.calendar_url)
    raw_url = record.get("url")
    if raw_url is not None and str(raw_url).strip():
        event_url = _resolve_https(raw_url, venue.calendar_url)
        if event_url is None:
            return None
    else:
        event_url = offer_url or venue.calendar_url

    image = _parse_image(record.get("image"), venue.calendar_url)
    performer_names = _parse_performers(record)
    concert = Concert(
        id=_event_id(venue, date, local_time, event_url, name),
        name=name,
        url=event_url,
        source="venue_calendar",
        sold_out=sold_out,
        artists=[],
        date=date,
        time=local_time,
        time_zone=venue.time_zone,
        venue=venue.name,
        city=venue.city,
        region=venue.region,
        price=price,
        image=image,
    )
    return ExtractedEvent(
        concert=concert,
        performer_names=performer_names,
        latitude=venue.lat,
        longitude=venue.lon,
    )


def extract_events(
    document: str, venue: UndergroundVenue, now: dt.datetime
) -> list[ExtractedEvent]:
    """Extract upcoming MusicEvents from an HTML page or JSON-LD payload."""
    nodes: list[dict[str, Any]] = []
    for block in _extract_blocks(document):
        try:
            payload = json.loads(block)
        except ValueError:
            logger.warning("Skipping malformed JSON-LD block for %s", venue.slug)
            continue
        _collect_music_events(payload, nodes)

    events: dict[str, ExtractedEvent] = {}
    for node in nodes:
        if extracted := parse_event(node, venue, now):
            events[extracted.concert.id] = extracted
    return list(events.values())


async def fetch_calendar(
    client: httpx.AsyncClient, venue: UndergroundVenue, now: dt.datetime
) -> list[ExtractedEvent]:
    """Fetch one curated venue's public HTTPS calendar and extract MusicEvents."""
    if urlsplit(venue.calendar_url).scheme != "https":
        raise JsonLdError("non-https calendar URL")
    try:
        response = await client.get(venue.calendar_url)
        response.raise_for_status()
        if len(response.content) > MAX_BODY_BYTES:
            raise JsonLdError("response too large")
        body = response.text
    except JsonLdError:
        raise
    except httpx.HTTPStatusError as exc:
        raise JsonLdError(f"HTTP {exc.response.status_code}") from None
    except httpx.HTTPError as exc:
        raise JsonLdError(type(exc).__name__) from None
    return extract_events(body, venue, now)
