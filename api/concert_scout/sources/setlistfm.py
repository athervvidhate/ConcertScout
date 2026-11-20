import datetime as dt
import re
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlsplit, urlunsplit

import httpx
from httpx_retries import Retry, RetryTransport
from pydantic import BaseModel
from redis.asyncio import Redis

from concert_scout import cache, limits
from concert_scout.models import Text
from concert_scout.names import normalize
from concert_scout.sources import http

BASE_URL = "https://api.setlist.fm/rest/1.0"
CACHE_TTL = dt.timedelta(days=7)
MAX_SHOWS = 5
MIN_SONGS = 3
MAX_STAPLES = 8

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
_ALLOWED_HOSTS = frozenset({"www.setlist.fm", "setlist.fm"})
_STATE_CODE_COUNTRIES = frozenset({"US", "CA", "AU"})


class SetlistfmError(Exception):
    """Setlist.fm failed. Never includes API credentials."""


class SetlistShow(BaseModel):
    """The most recent completed Concert in the Setlist.fm summary."""

    date: dt.date
    venue: Text | None = None
    city: Text | None = None


class SetlistStaple(BaseModel):
    """A song played across recent live setlists."""

    name: Text
    shows: int
    encore_shows: int = 0


class SetlistSummary(BaseModel):
    """Recent live setlist summary computed strictly from Setlist.fm source records."""

    artist: Text
    mbid: str | None = None
    show_count: int = 0
    average_songs: int | None = None
    encore_shows: int = 0
    last_show: SetlistShow | None = None
    staples: list[SetlistStaple] = []
    source_url: str | None = None


@dataclass(frozen=True)
class _ParsedShow:
    date: dt.date
    venue: str | None
    city: str | None
    songs: list[tuple[str, bool]]
    has_encore: bool
    artist_name: str
    artist_mbid: str | None
    artist_url: str | None
    setlist_url: str | None


def _as_dict(value: Any) -> dict[str, Any] | None:
    return cast(dict[str, Any], value) if isinstance(value, dict) else None


def _as_list(value: Any) -> list[Any] | None:
    return cast(list[Any], value) if isinstance(value, list) else None


def make_client(
    api_key: str, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=BASE_URL,
        headers={
            "User-Agent": http.USER_AGENT,
            "Accept": "application/json",
            "x-api-key": api_key,
        },
        timeout=10.0,
        transport=RetryTransport(transport, retry=Retry(total=2, backoff_factor=0.5)),
    )


def valid_mbid(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    return cleaned.lower() if _UUID_RE.fullmatch(cleaned) else None


def safe_source_url(raw: Any) -> str | None:
    """Only allow links back to Setlist.fm over HTTPS."""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    parsed = urlsplit(text)
    if parsed.scheme not in ("https", "http"):
        return None
    host = (parsed.hostname or "").lower()
    if host not in _ALLOWED_HOSTS or not parsed.path.startswith("/"):
        return None
    return urlunsplit(("https", host, parsed.path, parsed.query, ""))


async def artist_setlist(
    client: httpx.AsyncClient,
    redis: Redis,
    name: str,
    *,
    mbid: str | None = None,
) -> SetlistSummary:
    """Lazy setlist summary for one Artist. Cached in Redis for 7 days."""
    clean_mbid = valid_mbid(mbid)
    key = f"setlist:mbid:{clean_mbid}" if clean_mbid else f"setlist:name:{normalize(name)}"
    if cached := await cache.read(redis, key, SetlistSummary):
        return cached

    await limits.setlistfm_call(redis)
    try:
        if clean_mbid:
            response = await client.get(f"/artist/{clean_mbid}/setlists", params={"p": 1})
        else:
            response = await client.get("/search/setlists", params={"artistName": name, "p": 1})
        if response.status_code == 404:
            summary = SetlistSummary(artist=name, mbid=clean_mbid)
        else:
            response.raise_for_status()
            summary = parse_setlists(
                name, response.json(), mbid=clean_mbid, exact_name=clean_mbid is None
            )
    except httpx.HTTPStatusError as exc:
        raise SetlistfmError(f"status {exc.response.status_code}") from None
    except httpx.HTTPError as exc:
        raise SetlistfmError(type(exc).__name__) from None
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise SetlistfmError(f"unreadable response: {type(exc).__name__}") from None

    await cache.write(redis, key, summary, CACHE_TTL)
    return summary


def parse_setlists(
    artist_name: str,
    body: dict[str, Any],
    *,
    mbid: str | None = None,
    exact_name: bool = False,
    today: dt.date | None = None,
) -> SetlistSummary:
    """Compute Setlist DNA strictly from source records, with zero LLM involvement."""
    raw_items = _as_list(body.get("setlist"))
    if raw_items is None:
        return SetlistSummary(artist=artist_name, mbid=mbid)

    cutoff = (today or dt.datetime.now(dt.UTC).date()) + dt.timedelta(days=1)
    wanted = normalize(artist_name)
    pinned_mbid: str | None = mbid

    parsed: list[_ParsedShow] = []
    for raw_item in raw_items:
        item = _as_dict(raw_item)
        if item is None:
            continue
        artist_obj = _as_dict(item.get("artist"))
        if artist_obj is None:
            continue
        item_artist_name = str(artist_obj.get("name") or "").strip()
        raw_mbid = artist_obj.get("mbid")
        item_mbid = valid_mbid(raw_mbid if isinstance(raw_mbid, str) else None)
        if exact_name:
            if not item_artist_name or normalize(item_artist_name) != wanted:
                continue
            if pinned_mbid is None and item_mbid is not None:
                pinned_mbid = item_mbid
            elif pinned_mbid is not None and item_mbid is not None and item_mbid != pinned_mbid:
                continue

        event_date = _parse_event_date(item.get("eventDate"))
        if event_date is None or event_date > cutoff:
            continue

        songs, has_encore = _extract_songs(item)
        if len(songs) < MIN_SONGS:
            continue

        venue_obj = _as_dict(item.get("venue"))
        venue_name = (
            str(venue_obj.get("name") or "").strip() or None if venue_obj is not None else None
        )
        city_obj = _as_dict(venue_obj.get("city")) if venue_obj is not None else None
        parsed.append(
            _ParsedShow(
                date=event_date,
                venue=venue_name,
                city=_format_city(city_obj),
                songs=songs,
                has_encore=has_encore,
                artist_name=item_artist_name or artist_name,
                artist_mbid=item_mbid,
                artist_url=safe_source_url(artist_obj.get("url")),
                setlist_url=safe_source_url(item.get("url")),
            )
        )

    if not parsed:
        return SetlistSummary(artist=artist_name, mbid=mbid)

    parsed.sort(key=lambda show: show.date, reverse=True)
    recent = parsed[:MAX_SHOWS]
    show_count = len(recent)
    average_songs = round(sum(len(show.songs) for show in recent) / show_count)
    encore_shows = sum(1 for show in recent if show.has_encore)

    appearances: dict[str, int] = {}
    encore_counts: dict[str, int] = {}
    display_names: dict[str, str] = {}
    first_seen: dict[str, tuple[int, int]] = {}

    for show_idx, show in enumerate(recent):
        seen_in_show: set[str] = set()
        encore_in_show: set[str] = set()
        for song_idx, (title, is_encore) in enumerate(show.songs):
            key = normalize(title)
            if not key:
                continue
            if key not in display_names:
                display_names[key] = title
                first_seen[key] = (show_idx, song_idx)
            if key not in seen_in_show:
                seen_in_show.add(key)
                appearances[key] = appearances.get(key, 0) + 1
            if is_encore and key not in encore_in_show:
                encore_in_show.add(key)
                encore_counts[key] = encore_counts.get(key, 0) + 1

    ranked_keys = sorted(
        appearances,
        key=lambda k: (
            -appearances[k],
            first_seen[k][0],
            first_seen[k][1],
            display_names[k].lower(),
        ),
    )[:MAX_STAPLES]
    staples = [
        SetlistStaple(
            name=display_names[key],
            shows=appearances[key],
            encore_shows=encore_counts.get(key, 0),
        )
        for key in ranked_keys
    ]

    latest = recent[0]
    source_url = next((s.artist_url for s in recent if s.artist_url), None) or next(
        (s.setlist_url for s in recent if s.setlist_url), None
    )
    resolved_mbid = mbid or next((s.artist_mbid for s in recent if s.artist_mbid), None)

    return SetlistSummary(
        artist=latest.artist_name,
        mbid=resolved_mbid,
        show_count=show_count,
        average_songs=average_songs,
        encore_shows=encore_shows,
        last_show=SetlistShow(date=latest.date, venue=latest.venue, city=latest.city),
        staples=staples,
        source_url=source_url,
    )


def _parse_event_date(raw: Any) -> dt.date | None:
    if not isinstance(raw, str):
        return None
    try:
        return dt.datetime.strptime(raw.strip(), "%d-%m-%Y").date()
    except ValueError:
        return None


def _format_city(city: dict[str, Any] | None) -> str | None:
    if not city:
        return None
    name = str(city.get("name") or "").strip()
    if not name:
        return None
    country = _as_dict(city.get("country"))
    country_code = str(country.get("code") or "").strip().upper() if country else ""
    country_name = str(country.get("name") or "").strip() if country else ""
    state_code = str(city.get("stateCode") or "").strip()
    if country_code in _STATE_CODE_COUNTRIES and state_code:
        return f"{name}, {state_code}"
    if country_name:
        return f"{name}, {country_name}"
    return name


def _extract_songs(record: dict[str, Any]) -> tuple[list[tuple[str, bool]], bool]:
    sets_obj = _as_dict(record.get("sets"))
    if sets_obj is None:
        return [], False
    blocks = _as_list(sets_obj.get("set"))
    if blocks is None:
        return [], False

    songs: list[tuple[str, bool]] = []
    has_encore = False
    for raw_block in blocks:
        block = _as_dict(raw_block)
        if block is None:
            continue
        is_encore = bool(block.get("encore"))
        raw_songs = _as_list(block.get("song"))
        if raw_songs is None:
            continue
        for raw_song in raw_songs:
            song = _as_dict(raw_song)
            if song is None or song.get("tape"):
                continue
            title = str(song.get("name") or "").strip()
            if not title:
                continue
            songs.append((title, is_encore))
            if is_encore:
                has_encore = True
    return songs, has_encore
