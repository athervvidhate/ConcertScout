import datetime as dt
import hashlib
import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

import httpx
from pydantic import BaseModel
from redis.asyncio import Redis

from concert_scout import cache
from concert_scout.names import normalize
from concert_scout.sources import http

BASE_URL = "https://www.googleapis.com/youtube/v3"
PAGE_SIZE = 50
MAX_PAGES = 4
MAX_ARTISTS = 50
MAX_NAME_LENGTH = 200
CACHE_TTL = dt.timedelta(hours=1)

ALLOWED_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"})
ALLOWED_PATHS = frozenset({"/playlist", "/watch"})
PLAYLIST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
PRIVATE_SYSTEM_LISTS = frozenset({"WL", "LL"})

TOPIC_SUFFIX = re.compile(r"\s*-\s*Topic$", re.IGNORECASE)
VEVO_SUFFIX = re.compile(r"\s*VEVO$", re.IGNORECASE)
TITLE_SPLIT = re.compile(r"\s+[-–—]\s+")
BRACKETED_TAG = re.compile(
    r"\s*[\(\[]\s*(?:official|audio|video|lyric|lyrics|music\s+video|visualizer|"
    r"hd|4k|hq|live|remaster(?:ed)?|explicit|clean|audio\s+only|full\s+album|"
    r"feat\.?|ft\.?|featuring|prod\.?)[^\)\]]*[\)\]]",
    re.IGNORECASE,
)
INLINE_FEAT = re.compile(r"\s+(?:feat\.?|ft\.?|featuring)\b.*$", re.IGNORECASE)
CAMEL_BOUNDARY = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

UNAVAILABLE_TITLES = frozenset({"deleted video", "private video"})
IGNORED_ARTISTS = frozenset(
    {
        "deleted video",
        "private video",
        "various artists",
        "release",
        "topic",
        "official",
        "audio",
        "video",
        "unknown",
    }
)
QUOTA_REASONS = frozenset(
    {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded", "userRateLimitExceeded"}
)
PRIVATE_REASONS = frozenset({"playlistItemsNotAccessible", "forbidden"})


class YouTubeError(Exception):
    """YouTube failed. Messages never hold the playlist URL, playlist ID, or API key."""


class InvalidPlaylistUrl(Exception):
    """The supplied URL is not a valid YouTube or YouTube Music playlist URL."""


class PlaylistNotFound(Exception):
    """No public or unlisted playlist exists for that link."""


class PlaylistPrivate(Exception):
    """The playlist is private and cannot be read without sign-in."""


class QuotaExceeded(Exception):
    """The YouTube Data API daily quota has been reached."""


class CachedPlaylistArtists(BaseModel):
    artists: list[str]


def make_client(
    api_key: str, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    return http.make_client(BASE_URL, {"key": api_key}, transport)


def parse_playlist_id(url: str) -> str:
    """Validate a YouTube or YouTube Music playlist URL and return its playlist ID."""
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise InvalidPlaylistUrl
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise InvalidPlaylistUrl
    path = parsed.path.rstrip("/")
    if path not in ALLOWED_PATHS:
        raise InvalidPlaylistUrl
    values = parse_qs(parsed.query, keep_blank_values=False).get("list")
    if not values or len(values) != 1:
        raise InvalidPlaylistUrl
    playlist_id = values[0].strip()
    if playlist_id.upper() in PRIVATE_SYSTEM_LISTS:
        raise PlaylistPrivate
    if not PLAYLIST_ID_PATTERN.match(playlist_id):
        raise InvalidPlaylistUrl
    return playlist_id


def cache_key(playlist_id: str) -> str:
    """Hash the playlist ID so raw IDs and URLs never appear in Redis keys."""
    digest = hashlib.sha256(playlist_id.encode()).hexdigest()
    return f"taste:youtube:{digest}"


def _clean_name(raw: str) -> str | None:
    text = unicodedata.normalize("NFC", raw)
    text = BRACKETED_TAG.sub("", text)
    text = INLINE_FEAT.sub("", text)
    text = " ".join(text.strip(" \"'“”‘’|-–—:").split())
    if not text or len(text) > MAX_NAME_LENGTH:
        return None
    if normalize(text) in IGNORED_ARTISTS:
        return None
    return text


def _collapsed(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    unaccented = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\W+", "", unaccented).casefold()


def _title_artist(title: str) -> str | None:
    if title.strip().casefold() in UNAVAILABLE_TITLES:
        return None
    parts = TITLE_SPLIT.split(title, maxsplit=1)
    if len(parts) < 2:
        return None
    return _clean_name(parts[0])


def _vevo_artist(owner: str, title: str) -> str | None:
    stripped = VEVO_SUFFIX.sub("", owner).strip()
    if not stripped:
        return None
    if " " not in stripped:
        # CamelCase or run-together VEVO handles like "TameImpalaVEVO" or "billieeilishVEVO"
        # recover exact spacing from the track title when the artist matches.
        from_title = _title_artist(title)
        if from_title and _collapsed(from_title) == _collapsed(stripped):
            return from_title
        spaced = CAMEL_BOUNDARY.sub(" ", stripped)
        return _clean_name(spaced)
    return _clean_name(stripped)


def extract_artist(snippet: Mapping[str, Any]) -> tuple[str, int] | None:
    """Return `(artist_name, priority)` for one playlist item snippet, or None to skip it.

    Preference order:
    1. `videoOwnerChannelTitle` ending in `" - Topic"` (priority 2) or `"VEVO"` (priority 1).
    2. `"Artist - Track"` parsing from `title` (priority 0).
    """
    raw_title = snippet.get("title")
    title = raw_title if isinstance(raw_title, str) else ""
    if title.strip().casefold() in UNAVAILABLE_TITLES:
        return None

    raw_owner = snippet.get("videoOwnerChannelTitle")
    owner = raw_owner.strip() if isinstance(raw_owner, str) else ""
    if owner:
        if TOPIC_SUFFIX.search(owner):
            candidate = _clean_name(TOPIC_SUFFIX.sub("", owner))
            if candidate:
                return (candidate, 2)
        elif VEVO_SUFFIX.search(owner):
            candidate = _vevo_artist(owner, title)
            if candidate:
                return (candidate, 1)

    if title:
        candidate = _title_artist(title)
        if candidate:
            return (candidate, 0)
    return None


def rank_artists(items: Sequence[Mapping[str, Any]], limit: int = MAX_ARTISTS) -> list[str]:
    """Extract, deduplicate by normalized name, and rank Artists by frequency."""
    counts: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    best_name: dict[str, tuple[int, str]] = {}

    for index, item in enumerate(items):
        snippet = item.get("snippet")
        if not isinstance(snippet, Mapping):
            continue
        extracted = extract_artist(cast(Mapping[str, Any], snippet))
        if not extracted:
            continue
        name, priority = extracted
        key = normalize(name)
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
        if key not in first_seen:
            first_seen[key] = index
            best_name[key] = (priority, name)
        elif priority > best_name[key][0]:
            best_name[key] = (priority, name)

    ordered = sorted(counts, key=lambda key: (-counts[key], first_seen[key]))
    return [best_name[key][1] for key in ordered[:limit]]


def error_reasons(response: httpx.Response) -> set[str]:
    try:
        raw: Any = response.json()
    except ValueError:
        return set()
    if not isinstance(raw, dict):
        return set()
    body = cast(dict[str, Any], raw)
    error = body.get("error")
    if not isinstance(error, dict):
        return set()
    entries = cast(dict[str, Any], error).get("errors")
    if not isinstance(entries, list):
        return set()
    reasons: set[str] = set()
    for entry in cast(list[Any], entries):
        if isinstance(entry, dict):
            reason = cast(dict[str, Any], entry).get("reason")
            if isinstance(reason, str):
                reasons.add(reason)
    return reasons


def _raise_for_api_error(response: httpx.Response) -> None:
    reasons = error_reasons(response)
    if response.status_code == 404 or "playlistNotFound" in reasons:
        raise PlaylistNotFound
    if response.status_code == 429 or reasons & QUOTA_REASONS:
        raise QuotaExceeded
    if response.status_code == 403 and reasons & PRIVATE_REASONS:
        raise PlaylistPrivate
    raise YouTubeError(f"status {response.status_code}")


async def fetch_playlist_items(
    client: httpx.AsyncClient, playlist_id: str, max_pages: int = MAX_PAGES
) -> list[dict[str, Any]]:
    """Fetch pages of 50 via `playlistItems.list` only, never `search.list`. Four by default."""
    collected: list[dict[str, Any]] = []
    page_token: str | None = None

    for _ in range(max_pages):
        params: dict[str, str] = {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": str(PAGE_SIZE),
        }
        if page_token:
            params["pageToken"] = page_token
        try:
            response = await client.get("/playlistItems", params=params)
            if response.status_code >= 400:
                _raise_for_api_error(response)
            raw: Any = response.json()
            if not isinstance(raw, dict):
                raise YouTubeError("unreadable response: non-object")
            body = cast(dict[str, Any], raw)
            raw_items = body.get("items", [])
            if not isinstance(raw_items, list):
                raise YouTubeError("unreadable response: items")
            items = cast(list[Any], raw_items)
            collected.extend(cast(dict[str, Any], item) for item in items if isinstance(item, dict))
            next_token = body.get("nextPageToken")
            page_token = next_token if isinstance(next_token, str) and next_token else None
        except (PlaylistNotFound, PlaylistPrivate, QuotaExceeded, YouTubeError):
            raise
        except httpx.HTTPError as exc:
            raise YouTubeError(type(exc).__name__) from None
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise YouTubeError(f"unreadable response: {type(exc).__name__}") from None

        if not page_token or not items:
            break

    return collected


async def playlist_artists(
    client: httpx.AsyncClient, redis: Redis, url: str, limit: int = MAX_ARTISTS
) -> list[str]:
    """Read a public YouTube or YouTube Music playlist into ranked Artist names."""
    playlist_id = parse_playlist_id(url)
    key = cache_key(playlist_id)
    if cached := await cache.read(redis, key, CachedPlaylistArtists):
        return cached.artists[:limit]

    items = await fetch_playlist_items(client, playlist_id)
    artists = rank_artists(items, MAX_ARTISTS)
    if artists:
        await cache.write(redis, key, CachedPlaylistArtists(artists=artists), CACHE_TTL)
    return artists[:limit]
