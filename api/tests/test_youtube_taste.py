"""YouTube playlist Taste import contracts: URL validation, extraction, quota, cache, and route."""

import hashlib
import json
import logging
from typing import Any, cast
from unittest.mock import AsyncMock

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from pydantic import SecretStr

from concert_scout import limits
from concert_scout.sources import youtube
from tests.contracts import install_sources
from tests.test_app import api_for

PUBLIC_PLAYLIST_ID = "PL9tY0BWXOZFtSecretPlaylist123"
PUBLIC_URL = f"https://www.youtube.com/playlist?list={PUBLIC_PLAYLIST_ID}"
MUSIC_URL = f"https://music.youtube.com/playlist?list={PUBLIC_PLAYLIST_ID}"
API_KEY = "youtube-secret-api-key-12345"


@pytest.fixture(autouse=True)
def sources(monkeypatch: pytest.MonkeyPatch) -> None:
    install_sources(monkeypatch)


def _item(
    title: str,
    owner: str | None = None,
    playlist_owner: str = "Playlist Creator Channel",
) -> dict[str, Any]:
    snippet: dict[str, Any] = {"title": title, "channelTitle": playlist_owner}
    if owner is not None:
        snippet["videoOwnerChannelTitle"] = owner
    return {"snippet": snippet}


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (PUBLIC_URL, PUBLIC_PLAYLIST_ID),
        (f"https://youtube.com/playlist?list={PUBLIC_PLAYLIST_ID}", PUBLIC_PLAYLIST_ID),
        (f"https://m.youtube.com/playlist?list={PUBLIC_PLAYLIST_ID}", PUBLIC_PLAYLIST_ID),
        (MUSIC_URL, PUBLIC_PLAYLIST_ID),
        (
            f"https://www.youtube.com/watch?v=dQw4w9WgXcQ&list={PUBLIC_PLAYLIST_ID}&index=2",
            PUBLIC_PLAYLIST_ID,
        ),
        (
            "https://music.youtube.com/playlist?list=RDCLAK5uy_kset8DisdE7LSD4TNjEVvrKRTmG7a56sY",
            "RDCLAK5uy_kset8DisdE7LSD4TNjEVvrKRTmG7a56sY",
        ),
        (
            "https://music.youtube.com/playlist?list=OLAK5uy_n234567890abcdef",
            "OLAK5uy_n234567890abcdef",
        ),
    ],
)
def test_parse_playlist_id_accepts_valid_youtube_urls(url: str, expected: str) -> None:
    assert youtube.parse_playlist_id(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not a url",
        "https://example.com/playlist?list=PL1234567890",
        "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/channel/UC1234567890?list=PL1234567890",
        "https://www.youtube.com/playlist?list=",
        "https://www.youtube.com/playlist?list=short",
        "https://www.youtube.com/playlist?list=PLbad!chars",
        "ftp://www.youtube.com/playlist?list=PL1234567890",
        "https://user:pass@www.youtube.com/playlist?list=PL1234567890",
        "https://evil-youtube.com/playlist?list=PL1234567890",
    ],
)
def test_parse_playlist_id_rejects_invalid_urls(url: str) -> None:
    with pytest.raises(youtube.InvalidPlaylistUrl):
        youtube.parse_playlist_id(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/playlist?list=WL",
        "https://music.youtube.com/playlist?list=LL",
    ],
)
def test_parse_playlist_id_flags_personal_system_playlists_as_private(url: str) -> None:
    with pytest.raises(youtube.PlaylistPrivate):
        youtube.parse_playlist_id(url)


def test_artist_extraction_prefers_topic_and_vevo_and_falls_back_to_title() -> None:
    items = [
        # - Topic channel preferred over title
        _item("White Gloves", owner="Khruangbin - Topic"),
        _item("Time (You and I)", owner="Khruangbin - Topic"),
        # VEVO CamelCase matched with title spacing
        _item("Tame Impala - The Less I Know The Better (Official Video)", owner="TameImpalaVEVO"),
        # VEVO CamelCase with no dash in title
        _item("Tití Me Preguntó (Official Video)", owner="BadBunnyVEVO"),
        # VEVO with spaces
        _item("Get Lucky (Official Audio)", owner="Daft Punk VEVO"),
        # Various Artists - Topic falls back to title parsing
        _item("Radiohead – Karma Police [Official Audio]", owner="Various Artists - Topic"),
        # Standard Artist - Track with featured artist and official tags
        _item(
            "Fred again.. feat. The Blessed Madonna — Marea (Official Video)",
            owner="RandomUploader",
        ),
        _item("Kendrick Lamar ft. SZA - All The Stars (Official Music Video)", owner="FanChannel"),
        # Deleted / Private / non-music entries skipped; playlist owner never extracted
        _item("Deleted video"),
        _item("Private video"),
        _item("My Summer Vlog 2026", owner="RandomVlogger"),
    ]
    artists = youtube.rank_artists(items)
    assert artists == [
        "Khruangbin",
        "Tame Impala",
        "Bad Bunny",
        "Daft Punk",
        "Radiohead",
        "Fred again..",
        "Kendrick Lamar",
    ]
    assert "Playlist Creator Channel" not in artists
    assert "RandomVlogger" not in artists
    assert "Various Artists" not in artists


def test_ranking_by_frequency_dedup_by_normalized_name_and_50_artist_cap() -> None:
    items: list[dict[str, Any]] = [
        _item("the strokes - Last Nite", owner="RandomUpload"),
        _item("Reptilia", owner="The Strokes - Topic"),
        _item("Someday", owner="The Strokes - Topic"),
        _item("Strokes - Hard To Explain", owner="AnotherChannel"),
        _item("Four Tet - Baby", owner="FanChannel"),
        _item("Loved", owner="Four Tet - Topic"),
        _item("Radiohead - Creep", owner="FanChannel"),
    ]
    # Add 55 more unique Artists once each so total distinct Artists > 50.
    for idx in range(55):
        items.append(_item(f"Track {idx}", owner=f"Extra Artist {idx:02d} - Topic"))

    artists = youtube.rank_artists(items)
    assert len(artists) == 50
    # Highest frequency first; "- Topic" casing wins for deduplicated "The Strokes".
    assert artists[:3] == ["The Strokes", "Four Tet", "Radiohead"]
    assert sum("strokes" in name.casefold() for name in artists) == 1


async def test_fetch_uses_only_playlist_items_and_stops_after_4_pages() -> None:
    seen_requests: list[tuple[str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append((request.url.path, dict(request.url.params)))
        page_num = len(seen_requests)
        items = [
            _item(f"Song {page_num}-{i}", owner=f"Artist {page_num} - Topic") for i in range(50)
        ]
        # Always provide nextPageToken to verify we hard-stop at 4 pages (200 items).
        return httpx.Response(200, json={"items": items, "nextPageToken": f"token-{page_num + 1}"})

    async with youtube.make_client(API_KEY, httpx.MockTransport(handler)) as client:
        items = await youtube.fetch_playlist_items(client, PUBLIC_PLAYLIST_ID)

    assert len(seen_requests) == 4
    assert len(items) == 200
    for index, (path, params) in enumerate(seen_requests, start=1):
        assert path == "/youtube/v3/playlistItems"
        assert "search" not in path
        assert params["part"] == "snippet"
        assert params["playlistId"] == PUBLIC_PLAYLIST_ID
        assert params["maxResults"] == "50"
        if index > 1:
            assert params["pageToken"] == f"token-{index}"


async def test_playlist_artists_caches_1_hour_by_hashed_id_without_storing_url_or_titles() -> None:
    calls = 0
    secret_title = "VeryPrivateVideoTitleThatMustNotBeCached"

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={"items": [_item(secret_title, owner="Khruangbin - Topic")]},
        )

    redis = FakeAsyncRedis()
    async with youtube.make_client(API_KEY, httpx.MockTransport(handler)) as client:
        first = await youtube.playlist_artists(client, redis, PUBLIC_URL)
        # Equivalent YouTube Music URL for the same playlist ID hits the same cache entry.
        second = await youtube.playlist_artists(client, redis, MUSIC_URL)

    assert first == ["Khruangbin"]
    assert second == ["Khruangbin"]
    assert calls == 1

    expected_key = f"taste:youtube:{hashlib.sha256(PUBLIC_PLAYLIST_ID.encode()).hexdigest()}"
    raw_keys = cast(list[bytes], await redis.keys("*"))  # pyright: ignore[reportUnknownMemberType]
    keys = [key.decode() for key in raw_keys]
    assert keys == [expected_key]
    ttl = await redis.ttl(expected_key)
    assert 3500 <= ttl <= 3600
    cached_value = await redis.get(expected_key)
    assert isinstance(cached_value, bytes)
    payload = cached_value.decode()
    assert json.loads(payload) == {"artists": ["Khruangbin"]}
    assert PUBLIC_PLAYLIST_ID not in expected_key
    assert PUBLIC_PLAYLIST_ID not in payload
    assert secret_title not in payload


@pytest.mark.parametrize(
    ("status_code", "reason", "expected"),
    [
        (404, "playlistNotFound", youtube.PlaylistNotFound),
        (403, "playlistItemsNotAccessible", youtube.PlaylistPrivate),
        (403, "forbidden", youtube.PlaylistPrivate),
        (403, "quotaExceeded", youtube.QuotaExceeded),
        (403, "dailyLimitExceeded", youtube.QuotaExceeded),
        (429, "rateLimitExceeded", youtube.QuotaExceeded),
        (403, "keyInvalid", youtube.YouTubeError),
        (500, "backendError", youtube.YouTubeError),
    ],
)
async def test_fetch_maps_youtube_api_errors_without_leaking_key_or_id(
    status_code: int, reason: str, expected: type[Exception]
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={"error": {"code": status_code, "errors": [{"reason": reason}]}},
        )

    async with youtube.make_client(API_KEY, httpx.MockTransport(handler)) as client:
        with pytest.raises(expected) as exc_info:
            await youtube.fetch_playlist_items(client, PUBLIC_PLAYLIST_ID)

    assert API_KEY not in str(exc_info.value)
    assert PUBLIC_PLAYLIST_ID not in str(exc_info.value)


async def test_route_returns_imported_taste_and_never_logs_playlist_url(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(
        youtube,
        "playlist_artists",
        AsyncMock(return_value=["Khruangbin", "Tame Impala"]),
    )
    with caplog.at_level(logging.DEBUG):
        async with api_for(youtube_api_key=SecretStr(API_KEY)) as api:
            response = await api.post("/taste/youtube-playlist", json={"url": PUBLIC_URL})

    assert response.status_code == 200
    assert response.json() == {"artists": ["Khruangbin", "Tame Impala"]}
    assert PUBLIC_URL not in caplog.text
    assert PUBLIC_PLAYLIST_ID not in caplog.text


@pytest.mark.parametrize(
    ("url", "side_effect", "status", "code", "snippet"),
    [
        ("https://example.com/not-youtube", None, 422, "invalid_playlist_url", "YouTube"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", None, 422, "invalid_playlist_url", "list="),
        (
            "https://www.youtube.com/playlist?list=WL",
            None,
            403,
            "playlist_private",
            "private",
        ),
        (
            PUBLIC_URL,
            youtube.PlaylistPrivate(),
            403,
            "playlist_private",
            "private",
        ),
        (
            PUBLIC_URL,
            youtube.PlaylistNotFound(),
            404,
            "playlist_not_found",
            "could not find",
        ),
        (
            PUBLIC_URL,
            youtube.QuotaExceeded(),
            503,
            "youtube_quota_exceeded",
            "daily limit",
        ),
        (
            PUBLIC_URL,
            youtube.YouTubeError("status 500"),
            503,
            "taste_unavailable",
            "not answering",
        ),
        (
            PUBLIC_URL,
            [],
            404,
            "taste_empty",
            "could not find any Artists",
        ),
    ],
)
async def test_route_returns_actionable_refusals_without_leaking_url(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    url: str,
    side_effect: Any,
    status: int,
    code: str,
    snippet: str,
) -> None:
    if isinstance(side_effect, Exception):
        monkeypatch.setattr(youtube, "playlist_artists", AsyncMock(side_effect=side_effect))
    elif side_effect is not None:
        monkeypatch.setattr(youtube, "playlist_artists", AsyncMock(return_value=side_effect))

    with caplog.at_level(logging.DEBUG):
        async with api_for(youtube_api_key=SecretStr(API_KEY)) as api:
            response = await api.post("/taste/youtube-playlist", json={"url": url})

    assert response.status_code == status
    body = response.json()
    assert body["code"] == code
    assert snippet.lower() in body["message"].lower()
    assert PUBLIC_PLAYLIST_ID not in response.text
    assert PUBLIC_PLAYLIST_ID not in caplog.text
    assert API_KEY not in response.text
    assert API_KEY not in caplog.text


async def test_route_empty_body_returns_invalid_playlist_url() -> None:
    async with api_for(youtube_api_key=SecretStr(API_KEY)) as api:
        response = await api.post("/taste/youtube-playlist", json={"url": "   "})
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_playlist_url"


async def test_route_unavailable_when_api_key_missing() -> None:
    async with api_for() as api:
        response = await api.post("/taste/youtube-playlist", json={"url": PUBLIC_URL})
    assert response.status_code == 503
    assert response.json()["code"] == "taste_unavailable"


async def test_route_enforces_taste_visitor_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limits, "TASTE_PER_HOUR", 2)
    monkeypatch.setattr(youtube, "playlist_artists", AsyncMock(return_value=["Khruangbin"]))
    redis = FakeAsyncRedis()
    async with api_for(redis, youtube_api_key=SecretStr(API_KEY)) as api:
        first = await api.post("/taste/youtube-playlist", json={"url": PUBLIC_URL})
        second = await api.post("/taste/youtube-playlist", json={"url": PUBLIC_URL})
        third = await api.post("/taste/youtube-playlist", json={"url": PUBLIC_URL})
    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.json()["code"] == "visitor_limit"
