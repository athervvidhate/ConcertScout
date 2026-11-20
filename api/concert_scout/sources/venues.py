"""Venue room character from MusicBrainz Places and Wikidata (ADR 0002).

Every fact (capacity, tier, venue type) comes from a verified source record. Unverified venues
return only the venue name, and capacity tiers are computed strictly in code.
"""

import datetime as dt
import logging
import math
import re
from typing import Any, Literal, cast

import httpx
from pydantic import BaseModel
from redis.asyncio import Redis

from concert_scout import cache, limits
from concert_scout.names import normalize
from concert_scout.sources import http

logger = logging.getLogger(__name__)

WIKIDATA_BASE_URL = "https://www.wikidata.org"
CACHE_TTL = dt.timedelta(days=60)
VENUE_PER_HOUR = 120
# Verified source coordinates must sit within this distance to avoid false namesake matches.
MAX_DISTANCE_KM = 1.0
MIN_SCORE = 85
EARTH_RADIUS_KM = 6371.0088

WIKIDATA_URL = re.compile(r"https?://(?:www\.)?wikidata\.org/(?:wiki|entity)/(Q\d+)", re.IGNORECASE)

# Well-known Wikidata P31 (instance of) classes for live music venues, so common rooms avoid an
# extra label lookup. Unknown venue P31 QIDs still read their English label directly from Wikidata.
VENUE_TYPE_LABELS: dict[str, str] = {
    "Q1060829": "Concert hall",
    "Q8719053": "Music venue",
    "Q1228895": "Live music club",
    "Q622425": "Nightclub",
    "Q24354": "Theater",
    "Q483110": "Stadium",
    "Q641226": "Arena",
    "Q1076486": "Sports venue",
    "Q54831": "Amphitheater",
    "Q3469910": "Performing arts center",
    "Q153562": "Opera house",
    "Q18674739": "Event venue",
    "Q17350442": "Venue",
    "Q1254933": "Ballroom",
    "Q187456": "Bar",
    "Q132241": "Festival venue",
}

# Structural P31 classes that describe a physical building rather than the room's character.
GENERIC_CLASSES = frozenset({"Q41176", "Q811979", "Q13226383", "Q2221906", "Q4830453"})

VenueTier = Literal[
    "Intimate club",
    "Club / Ballroom",
    "Theater",
    "Amphitheater / Large hall",
    "Arena / Stadium",
]


class VenueCharacter(BaseModel):
    """Verified room character for one venue. Any unverified fact stays None."""

    name: str
    city: str | None = None
    capacity: int | None = None
    tier: VenueTier | None = None
    venue_type: str | None = None
    mbid: str | None = None
    wikidata_id: str | None = None


class VenueLookupError(Exception):
    """A venue metadata source failed."""


def _as_dict(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _as_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [cast(dict[str, Any], item) for item in cast(list[Any], value) if isinstance(item, dict)]


def make_wikidata_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    return http.make_client(WIKIDATA_BASE_URL, {}, transport)


def venue_key(name: str, city: str | None = None) -> str:
    """Normalized key for a venue and optional city, used for Followed Venues and Alerts."""
    venue = normalize(name)
    if not venue:
        return ""
    place = normalize(city) if city else ""
    return f"{venue}::{place}" if place else venue


def cache_key(
    name: str, city: str | None = None, lat: float | None = None, lon: float | None = None
) -> str:
    coords = f"{lat:.3f},{lon:.3f}" if lat is not None and lon is not None else ""
    return f"venue:v1:{normalize(name)}:{normalize(city or '')}:{coords}"


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS-84 points in kilometers."""
    a, b = math.radians(lat1), math.radians(lat2)
    value = (
        math.sin((b - a) / 2) ** 2
        + math.cos(a) * math.cos(b) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.asin(min(1.0, math.sqrt(value)))


def capacity_tier(capacity: int | None) -> VenueTier | None:
    """Map a verified positive capacity into its factual room tier."""
    if capacity is None or capacity <= 0:
        return None
    if capacity <= 500:
        return "Intimate club"
    if capacity <= 1500:
        return "Club / Ballroom"
    if capacity <= 5000:
        return "Theater"
    if capacity <= 15000:
        return "Amphitheater / Large hall"
    return "Arena / Stadium"


async def cached_character(
    redis: Redis,
    name: str,
    city: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
) -> VenueCharacter | None:
    """Read a previously cached venue lookup without calling external sources."""
    return await cache.read(redis, cache_key(name, city, lat, lon), VenueCharacter)


async def lookup(
    musicbrainz: httpx.AsyncClient,
    wikidata: httpx.AsyncClient,
    redis: Redis,
    name: str,
    city: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
) -> VenueCharacter:
    """Lazily resolve a venue's verified room character, cached 60 days in Redis."""
    key = cache_key(name, city, lat, lon)
    if cached := await cache.read(redis, key, VenueCharacter):
        return cached

    unverified = VenueCharacter(name=name, city=city)
    if not normalize(name):
        return unverified

    had_error = False
    mb_place: dict[str, Any] | None = None
    mb_coords_verified = False
    qid: str | None = None

    try:
        places = await _search_musicbrainz_places(musicbrainz, redis, name)
        mb_place, mb_coords_verified = select_musicbrainz_place(places, name, city, lat, lon)
        if mb_place:
            qid = await _musicbrainz_wikidata_id(musicbrainz, redis, str(mb_place["id"]))
    except VenueLookupError as exc:
        logger.warning("MusicBrainz venue lookup failed: %s", exc)
        had_error = True

    entity: dict[str, Any] | None = None
    try:
        if qid:
            entity = await _fetch_wikidata_entity(wikidata, qid)
        elif lat is not None and lon is not None:
            qid, entity = await _search_wikidata_by_coords(wikidata, name, lat, lon)
    except VenueLookupError as exc:
        logger.warning("Wikidata venue lookup failed: %s", exc)
        had_error = True

    # Verify coordinates against the 1 km rule whenever source coordinates were supplied.
    wd_coords = parse_wikidata_coords(entity) if entity else None
    coords_ok = True
    if lat is not None and lon is not None:
        if wd_coords is not None:
            coords_ok = distance_km(lat, lon, wd_coords[0], wd_coords[1]) <= MAX_DISTANCE_KM
        else:
            coords_ok = mb_coords_verified

    if not coords_ok:
        result = unverified
    else:
        capacity = parse_wikidata_capacity(entity) if entity else None
        venue_type: str | None = None
        if entity:
            try:
                venue_type = await _resolve_venue_type(wikidata, entity)
            except VenueLookupError as exc:
                logger.warning("Wikidata venue type lookup failed: %s", exc)
                had_error = True
        if venue_type is None and mb_place:
            mb_type = mb_place.get("type")
            if isinstance(mb_type, str) and mb_type.strip():
                venue_type = mb_type.strip()

        verified = bool(mb_place or entity)
        result = VenueCharacter(
            name=name,
            city=city,
            capacity=capacity,
            tier=capacity_tier(capacity),
            venue_type=venue_type if verified else None,
            mbid=str(mb_place["id"]) if mb_place else None,
            wikidata_id=qid if entity else None,
        )

    if not had_error:
        await cache.write(redis, key, result, CACHE_TTL)
    return result


def select_musicbrainz_place(
    places: list[dict[str, Any]],
    name: str,
    city: str | None,
    lat: float | None,
    lon: float | None,
) -> tuple[dict[str, Any] | None, bool]:
    """Pick the best verified MusicBrainz Place. Returns `(place, coords_verified)`."""
    wanted = normalize(name)
    wanted_city = normalize(city) if city else ""
    exact: list[tuple[dict[str, Any], int, tuple[float, float] | None]] = []
    for place in places:
        score = int(place.get("score") or 0)
        if score < MIN_SCORE:
            continue
        names = [str(place.get("name") or "")]
        names.extend(str(a.get("name") or "") for a in _as_dicts(place.get("aliases")))
        if wanted not in (normalize(n) for n in names if n):
            continue
        exact.append((place, score, _parse_mb_coords(place.get("coordinates"))))

    if not exact:
        return None, False

    if lat is not None and lon is not None:
        within: list[tuple[float, int, dict[str, Any]]] = []
        without_coords: list[tuple[int, dict[str, Any]]] = []
        for place, score, coords in exact:
            if coords is not None:
                dist = distance_km(lat, lon, coords[0], coords[1])
                if dist <= MAX_DISTANCE_KM:
                    within.append((dist, -score, place))
            elif not wanted_city or _matches_city(place, wanted_city):
                without_coords.append((-score, place))
        if within:
            within.sort(key=lambda item: (item[0], item[1]))
            return within[0][2], True
        if len(without_coords) == 1:
            # Tentative: must still be verified by Wikidata P625 within 1 km.
            return without_coords[0][1], False
        return None, False

    if wanted_city:
        in_city = [(score, place) for place, score, _ in exact if _matches_city(place, wanted_city)]
        if len(in_city) == 1:
            return in_city[0][1], False
        if len(in_city) > 1:
            in_city.sort(key=lambda item: item[0], reverse=True)
            if in_city[0][0] - in_city[1][0] >= 5:
                return in_city[0][1], False
        return None, False

    # Neither coordinates nor city: only accept a single unambiguous exact match.
    return (exact[0][0], False) if len(exact) == 1 else (None, False)


def parse_wikidata_capacity(entity: dict[str, Any]) -> int | None:
    """Read P1083 (maximum capacity) from a Wikidata entity, preferring preferred-rank claims."""
    claims = _as_dict(entity.get("claims"))
    statements = _as_dicts(claims.get("P1083"))

    ranked: list[tuple[int, int]] = []
    for statement in statements:
        rank = statement.get("rank")
        if rank == "deprecated":
            continue
        value = _as_dict(
            _as_dict(_as_dict(statement.get("mainsnak")).get("datavalue")).get("value")
        )
        amount = value.get("amount")
        if not isinstance(amount, str):
            continue
        try:
            parsed = int(float(amount))
        except ValueError:
            continue
        if parsed > 0:
            priority = 0 if rank == "preferred" else 1
            ranked.append((priority, parsed))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0])
    return ranked[0][1]


def parse_wikidata_coords(entity: dict[str, Any]) -> tuple[float, float] | None:
    """Read P625 (coordinate location) from a Wikidata entity."""
    claims = _as_dict(entity.get("claims"))
    statements = _as_dicts(claims.get("P625"))

    for rank_target in ("preferred", "normal", None):
        for statement in statements:
            rank = statement.get("rank")
            if rank == "deprecated":
                continue
            if rank_target is not None and rank != rank_target:
                continue
            value = _as_dict(
                _as_dict(_as_dict(statement.get("mainsnak")).get("datavalue")).get("value")
            )
            lat, lon = value.get("latitude"), value.get("longitude")
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                return float(lat), float(lon)
    return None


def parse_wikidata_type_qids(entity: dict[str, Any]) -> list[str]:
    """Read P31 (instance of) QIDs from a Wikidata entity, non-deprecated first."""
    claims = _as_dict(entity.get("claims"))
    statements = _as_dicts(claims.get("P31"))

    qids: list[str] = []
    for statement in statements:
        if statement.get("rank") == "deprecated":
            continue
        value = _as_dict(
            _as_dict(_as_dict(statement.get("mainsnak")).get("datavalue")).get("value")
        )
        qid = value.get("id")
        if isinstance(qid, str) and qid.startswith("Q") and qid not in qids:
            qids.append(qid)
    return qids


def _parse_mb_coords(raw: Any) -> tuple[float, float] | None:
    coords = _as_dict(raw)
    lat, lon = coords.get("latitude"), coords.get("longitude")
    if not isinstance(lat, (int, float, str)) or not isinstance(lon, (int, float, str)):
        return None
    try:
        return float(lat), float(lon)
    except ValueError:
        return None


def _matches_city(place: dict[str, Any], wanted_city: str) -> bool:
    area = _as_dict(place.get("area"))
    area_name = normalize(str(area.get("name") or ""))
    if area_name and area_name == wanted_city:
        return True
    address = normalize(str(place.get("address") or ""))
    return bool(address and re.search(rf"\b{re.escape(wanted_city)}\b", address))


def _escaped(name: str) -> str:
    return name.replace("\\", "\\\\").replace('"', '\\"')


async def _search_musicbrainz_places(
    client: httpx.AsyncClient, redis: Redis, name: str
) -> list[dict[str, Any]]:
    await limits.musicbrainz_call(redis)
    params = {"query": f'place:"{_escaped(name)}"', "limit": 10}
    try:
        response = await client.get("/place", params=params)
        response.raise_for_status()
        return _as_dicts(_as_dict(response.json()).get("places"))
    except httpx.HTTPStatusError as exc:
        raise VenueLookupError(f"MusicBrainz status {exc.response.status_code}") from None
    except httpx.HTTPError as exc:
        raise VenueLookupError(f"MusicBrainz {type(exc).__name__}") from None
    except ValueError as exc:
        raise VenueLookupError(f"MusicBrainz unreadable: {type(exc).__name__}") from None


async def _musicbrainz_wikidata_id(
    client: httpx.AsyncClient, redis: Redis, mbid: str
) -> str | None:
    await limits.musicbrainz_call(redis)
    try:
        response = await client.get(f"/place/{mbid}", params={"inc": "url-rels"})
        response.raise_for_status()
        relations = _as_dicts(_as_dict(response.json()).get("relations"))
    except httpx.HTTPStatusError as exc:
        raise VenueLookupError(f"MusicBrainz place status {exc.response.status_code}") from None
    except httpx.HTTPError as exc:
        raise VenueLookupError(f"MusicBrainz place {type(exc).__name__}") from None
    except ValueError as exc:
        raise VenueLookupError(f"MusicBrainz place unreadable: {type(exc).__name__}") from None

    for relation in relations:
        resource = _as_dict(relation.get("url")).get("resource")
        if isinstance(resource, str) and (match := WIKIDATA_URL.search(resource)):
            return match.group(1)
    return None


async def _fetch_wikidata_entity(client: httpx.AsyncClient, qid: str) -> dict[str, Any] | None:
    params = {
        "action": "wbgetentities",
        "ids": qid,
        "props": "claims|labels|aliases",
        "languages": "en",
        "format": "json",
    }
    try:
        response = await client.get("/w/api.php", params=params)
        response.raise_for_status()
        entities = _as_dict(_as_dict(response.json()).get("entities"))
    except httpx.HTTPStatusError as exc:
        raise VenueLookupError(f"Wikidata status {exc.response.status_code}") from None
    except httpx.HTTPError as exc:
        raise VenueLookupError(f"Wikidata {type(exc).__name__}") from None
    except ValueError as exc:
        raise VenueLookupError(f"Wikidata unreadable: {type(exc).__name__}") from None
    entity = _as_dict(entities.get(qid))
    return entity if entity and "missing" not in entity else None


async def _search_wikidata_by_coords(
    client: httpx.AsyncClient, name: str, lat: float, lon: float
) -> tuple[str | None, dict[str, Any] | None]:
    search_params = {
        "action": "wbsearchentities",
        "search": name,
        "language": "en",
        "limit": 5,
        "format": "json",
    }
    try:
        response = await client.get("/w/api.php", params=search_params)
        response.raise_for_status()
        hits = _as_dicts(_as_dict(response.json()).get("search"))
    except httpx.HTTPStatusError as exc:
        raise VenueLookupError(f"Wikidata search status {exc.response.status_code}") from None
    except httpx.HTTPError as exc:
        raise VenueLookupError(f"Wikidata search {type(exc).__name__}") from None
    except ValueError as exc:
        raise VenueLookupError(f"Wikidata search unreadable: {type(exc).__name__}") from None

    qids = [str(hit["id"]) for hit in hits if hit.get("id")]
    if not qids:
        return None, None

    params = {
        "action": "wbgetentities",
        "ids": "|".join(qids),
        "props": "claims|labels|aliases",
        "languages": "en",
        "format": "json",
    }
    try:
        batch = await client.get("/w/api.php", params=params)
        batch.raise_for_status()
        entities = _as_dict(_as_dict(batch.json()).get("entities"))
    except httpx.HTTPStatusError as exc:
        raise VenueLookupError(f"Wikidata batch status {exc.response.status_code}") from None
    except httpx.HTTPError as exc:
        raise VenueLookupError(f"Wikidata batch {type(exc).__name__}") from None
    except ValueError as exc:
        raise VenueLookupError(f"Wikidata batch unreadable: {type(exc).__name__}") from None

    wanted = normalize(name)
    best: tuple[float, str, dict[str, Any]] | None = None
    for qid in qids:
        entity = _as_dict(entities.get(qid))
        if not entity or "missing" in entity:
            continue
        if not _entity_matches_name(entity, wanted):
            continue
        coords = parse_wikidata_coords(entity)
        if coords is None:
            continue
        dist = distance_km(lat, lon, coords[0], coords[1])
        if dist <= MAX_DISTANCE_KM and (best is None or dist < best[0]):
            best = (dist, qid, entity)
    return (best[1], best[2]) if best else (None, None)


def _entity_matches_name(entity: dict[str, Any], wanted: str) -> bool:
    names: list[str] = []
    label = _as_dict(_as_dict(entity.get("labels")).get("en")).get("value")
    if isinstance(label, str):
        names.append(label)
    for alias in _as_dicts(_as_dict(entity.get("aliases")).get("en")):
        alias_value = alias.get("value")
        if isinstance(alias_value, str):
            names.append(alias_value)
    return wanted in (normalize(n) for n in names)


async def _resolve_venue_type(client: httpx.AsyncClient, entity: dict[str, Any]) -> str | None:
    qids = parse_wikidata_type_qids(entity)
    if not qids:
        return None
    for qid in qids:
        if qid in VENUE_TYPE_LABELS:
            return VENUE_TYPE_LABELS[qid]
    preferred = [qid for qid in qids if qid not in GENERIC_CLASSES] or qids
    fetched = await _fetch_wikidata_entity(client, preferred[0])
    if not fetched:
        return None
    label = _as_dict(_as_dict(fetched.get("labels")).get("en")).get("value")
    return label.strip().capitalize() if isinstance(label, str) and label.strip() else None
