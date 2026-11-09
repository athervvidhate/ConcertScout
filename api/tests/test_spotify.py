"""OAuth/session/privacy contracts. Spotify is substituted only at its typed adapter boundary."""

import datetime as dt
import time
from typing import Any
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet
from fakeredis import FakeAsyncRedis
from pydantic import SecretStr
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel

from concert_scout import pipeline
from concert_scout.app import create_app
from concert_scout.models import Concert
from concert_scout.sources.spotify import Client, Credentials, SpotifyArtist, not_allowed
from concert_scout.spotify import (
    PREFIX,
    SESSION_COOKIE,
    SESSION_TTL,
    STATE_COOKIE,
    Sessions,
    artists_key,
    session_key,
)
from tests.contracts import CONCERTS, contract_model, forbidden_http, install_sources, settings_with

BY_ARTIST = [c for c in CONCERTS if c.artists[0].name == "Contract Artist"]

ORIGIN = "http://localhost:3000"
TOKEN = Credentials(
    access_token=SecretStr("private-access-token"),
    refresh_token=SecretStr("private-refresh-token"),
    expires_at=time.time() + 3600,
)
ARTISTS = [
    SpotifyArtist(
        name="Contract Artist", url="https://open.spotify.com/artist/contract", source="top"
    )
]


@pytest.fixture(autouse=True)
def typed_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    install_sources(monkeypatch)
    monkeypatch.setattr(Client, "exchange", AsyncMock(return_value=TOKEN))
    monkeypatch.setattr(Client, "artists", AsyncMock(return_value=ARTISTS))
    monkeypatch.setattr(Client, "check", AsyncMock())


def api_for(
    redis: FakeAsyncRedis,
    key: str,
    *,
    base_url: str = "http://127.0.0.1:8000",
    model: Model | None = None,
    **settings: Any,
) -> httpx.AsyncClient:
    app = create_app(
        settings_with(
            spotify_client_id="client-id",
            spotify_client_secret=SecretStr("client-secret"),
            spotify_encryption_key=SecretStr(key),
            **settings,
        ),
        httpx.MockTransport(forbidden_http),
        redis,
        model or contract_model(),
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url=base_url)


async def begin(api: httpx.AsyncClient) -> str:
    login = await api.get(PREFIX + "/login", params={"return_to": ORIGIN})
    assert login.status_code == 303
    url = urlsplit(login.headers["location"])
    fields = parse_qs(url.query)
    assert (url.scheme, url.netloc) == ("https", "accounts.spotify.com")
    assert fields["scope"] == ["user-top-read user-follow-read user-library-read"]
    assert fields["response_type"] == ["code"]
    assert fields["redirect_uri"] == [str(api.base_url).rstrip("/") + PREFIX + "/callback"]
    return fields["state"][0]


async def connect(api: httpx.AsyncClient) -> str:
    state = await begin(api)
    result = await api.get(PREFIX + "/callback", params={"code": "one-use-code", "state": state})
    assert result.status_code == 303
    assert result.headers["location"] == ORIGIN + "/?spotify=connected"
    cookie = api.cookies.get(SESSION_COOKIE)
    assert cookie
    return cookie


async def test_shelf_uses_exact_source_facts_without_any_model_and_disconnect_deletes_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = AsyncMock(side_effect=AssertionError("Spotify must never enter a model"))
    monkeypatch.setattr(pipeline, "interpret", model)
    redis, key = FakeAsyncRedis(), Fernet.generate_key().decode()
    model_calls: list[bool] = []

    def forbid_model(_: list[ModelMessage], __: AgentInfo) -> ModelResponse:
        model_calls.append(True)
        raise AssertionError("Spotify must not attempt any model request")

    async with api_for(redis, key, model=FunctionModel(forbid_model)) as api:
        session = await connect(api)
        encrypted = await redis.get(session_key(session))
        assert (
            isinstance(encrypted, bytes)
            and b"private-access-token" not in encrypted
            and b"private-refresh-token" not in encrypted
        )
        assert 0 < await redis.ttl(session_key(session)) <= SESSION_TTL
        response = await api.get(PREFIX + "/shelf", params={"place": "SF", "time_zone": "UTC"})
        assert response.status_code == 200
        assert "no-store" in response.headers["cache-control"]
        items = response.json()["concerts"]
        assert [i["concert"] for i in items] == [
            c.model_dump(mode="json", exclude_none=True) for c in BY_ARTIST
        ]
        assert all(i["artist"]["name"] == "Contract Artist" for i in items)
        disconnected = await api.post(PREFIX + "/disconnect", headers={"Origin": ORIGIN})
        assert disconnected.status_code == 204
        assert await redis.get(session_key(session)) is None
        assert await redis.get(artists_key(session)) is None
        assert api.cookies.get(SESSION_COOKIE) is None
        assert (await api.get(PREFIX + "/status")).json()["connected"] is False
    model.assert_not_awaited()
    assert model_calls == []


async def test_oauth_state_is_bound_to_the_browser_and_cannot_be_replayed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exchange = AsyncMock(return_value=TOKEN)
    monkeypatch.setattr(Client, "exchange", exchange)
    async with api_for(FakeAsyncRedis(), Fernet.generate_key().decode()) as api:
        state = await begin(api)
        refused = await api.get(PREFIX + "/callback", params={"state": "forged", "code": "code"})
        assert refused.status_code == 400
        exchange.assert_not_awaited()
        success = await api.get(PREFIX + "/callback", params={"state": state, "code": "code"})
        assert success.status_code == 303
        replay = await api.get(
            PREFIX + "/callback",
            params={"state": state, "code": "code"},
            headers={"Cookie": f"{STATE_COOKIE}={state}"},
        )
        assert replay.status_code == 400
        assert exchange.await_count == 1


async def test_non_allowlisted_users_get_a_clear_message_and_no_stored_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Client, "check", AsyncMock(side_effect=not_allowed()))
    redis = FakeAsyncRedis()
    async with api_for(redis, Fernet.generate_key().decode()) as api:
        state = await begin(api)
        response = await api.get(PREFIX + "/callback", params={"state": state, "code": "code"})
        assert response.headers["location"] == ORIGIN + "/?spotify=not_allowed"
        assert api.cookies.get(SESSION_COOKIE) is None
    assert await redis.execute_command("KEYS", "spotify:session:*") == []  # pyright: ignore[reportUnknownMemberType]


async def test_disconnect_requires_the_allowed_origin() -> None:
    redis = FakeAsyncRedis()
    async with api_for(redis, Fernet.generate_key().decode()) as api:
        session = await connect(api)
        refused = await api.post(PREFIX + "/disconnect", headers={"Origin": "https://evil.example"})
        assert refused.status_code == 403
        assert await redis.exists(session_key(session))


async def test_refresh_cannot_resurrect_a_concurrently_disconnected_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis, key = FakeAsyncRedis(), Fernet.generate_key().decode()
    async with api_for(redis, key) as api:
        session = await connect(api)
        # Expire only the access token, leaving the session and refresh token valid.
        await redis.delete(session_key(session))
        await Sessions(redis, key).save(session, TOKEN.model_copy(update={"expires_at": 0}))

        async def refresh(_: Credentials) -> Credentials:
            await redis.delete(session_key(session))
            return TOKEN

        monkeypatch.setattr(Client, "refresh", AsyncMock(side_effect=refresh))
        response = await api.get(PREFIX + "/shelf", params={"place": "SF", "time_zone": "UTC"})
        assert response.status_code == 401
        assert await redis.get(session_key(session)) is None


async def test_tampered_ciphertext_is_deleted_and_redirects_cannot_escape_the_allowlist() -> None:
    redis, key = FakeAsyncRedis(), Fernet.generate_key().decode()
    async with api_for(redis, key) as api:
        response = await api.get(PREFIX + "/login", params={"return_to": "https://evil.example"})
        assert response.status_code == 400
        session = await connect(api)
        await redis.set(session_key(session), b"tampered")
        assert (await api.get(PREFIX + "/status")).json()["connected"] is False
        assert await redis.get(session_key(session)) is None


def test_remote_http_redirect_is_rejected_but_loopback_is_allowed() -> None:
    with pytest.raises(ValueError):
        settings_with(spotify_redirect_uri="http://evil.example/auth/spotify/callback")
    with pytest.raises(ValueError):
        settings_with(spotify_redirect_uri="http://localhost:8000/auth/spotify/callback")
    assert settings_with().spotify_redirect_uri.startswith("http://127.0.0.1")


async def test_https_sessions_are_secure_http_only_and_scoped_away_from_search() -> None:
    async with api_for(
        FakeAsyncRedis(),
        Fernet.generate_key().decode(),
        base_url="https://api.example",
        spotify_redirect_uri="https://api.example/auth/spotify/callback",
    ) as api:
        await connect(api)
        cookie = next(cookie for cookie in api.cookies.jar if cookie.name == SESSION_COOKIE)
        assert cookie.secure and cookie.has_nonstandard_attr("HttpOnly")
        assert cookie.path == PREFIX


def test_invalid_public_configuration_never_echoes_other_secrets() -> None:
    from concert_scout.config import Settings

    fields: dict[str, Any] = {
        "_env_file": None,
        "tm_key": "private-tm",
        "anthropic_api_key": "private-model",
        "geoapify_key": "private-geo",
        "typesafe_api_key": "private-jev",
        "spotify_redirect_uri": "http://evil.example/auth/spotify/callback",
    }
    with pytest.raises(ValueError) as failure:
        Settings(**fields)
    assert "private-tm" not in str(failure.value)
    assert "private-jev" not in str(failure.value)
    assert "private-model" not in str(failure.value)


def test_exact_shelf_matching_does_not_turn_a_tribute_into_a_match() -> None:
    from concert_scout.models import Artist
    from concert_scout.spotify import exact_matches

    tribute = CONCERTS[0].model_copy(
        update={"id": "tribute", "artists": [Artist(name="A tribute to Contract Artist")]}
    )
    matched = exact_matches([tribute, *CONCERTS], ARTISTS)
    assert [item.concert.id for item in matched] == [c.id for c in BY_ARTIST]
    assert all(item.concert in BY_ARTIST for item in matched)


def test_the_shelf_gives_every_artist_a_turn_before_anyones_second_date() -> None:
    from concert_scout.models import Artist
    from concert_scout.spotify import exact_matches

    def show(id: str, name: str, day: int) -> Concert:
        return CONCERTS[0].model_copy(
            update={"id": id, "artists": [Artist(name=name)], "date": dt.date(2027, 1, day)}
        )

    favourite = SpotifyArtist(name="Favourite", url="https://open.spotify.com/1", source="top")
    liked = SpotifyArtist(name="Liked", url="https://open.spotify.com/2", source="liked")
    many = [show(f"residency-{day}", "Favourite", day) for day in range(1, 26)]
    matched = exact_matches([show("liked", "Liked", 28), *reversed(many)], [favourite, liked])
    assert [item.concert.id for item in matched[:3]] == ["residency-1", "liked", "residency-2"]
    assert len(matched) == 26


async def test_the_artist_list_is_cached_encrypted_and_never_outlives_a_disconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artists = AsyncMock(return_value=ARTISTS)
    monkeypatch.setattr(Client, "artists", artists)
    redis, key = FakeAsyncRedis(), Fernet.generate_key().decode()
    async with api_for(redis, key) as api:
        session = await connect(api)
        for _ in range(2):
            assert (
                await api.get(PREFIX + "/shelf", params={"place": "SF", "time_zone": "UTC"})
            ).status_code == 200
        assert artists.await_count == 1
        stored = await redis.get(artists_key(session))
        assert isinstance(stored, bytes) and b"Contract Artist" not in stored
    store = Sessions(redis, key)
    await redis.delete(session_key("gone"))
    await store.save_artists("gone", ARTISTS)
    assert await redis.exists(artists_key("gone")) == 0


async def test_a_search_genre_overrides_favourites_in_other_genres() -> None:
    from concert_scout.models import Artist
    from concert_scout.spotify import exact_matches

    summit = SpotifyArtist(name="John Summit", url="https://s/1", source="top")
    rapper = SpotifyArtist(name="Contract Rapper", url="https://s/2", source="liked")
    unknown = SpotifyArtist(name="No Genre", url="https://s/3", source="top")
    base = CONCERTS[0]
    house = base.model_copy(
        update={"id": "house", "artists": [Artist(name="John Summit", genre="Dance/Electronic")]}
    )
    rap = base.model_copy(
        update={"id": "rap", "artists": [Artist(name="Contract Rapper", genre="Hip-Hop/Rap")]}
    )
    blank = base.model_copy(update={"id": "blank", "artists": [Artist(name="No Genre")]})
    festival = base.model_copy(
        update={
            "id": "both",
            "artists": [
                Artist(name="John Summit", genre="Dance/Electronic"),
                Artist(name="Contract Rapper", genre="Hip-Hop/Rap"),
            ],
        }
    )
    concerts = [house, rap, blank, festival]
    favourites = [summit, rapper, unknown]

    assert {i.concert.id for i in exact_matches(concerts, favourites)} == {
        "house",
        "rap",
        "blank",
        "both",
    }
    filtered = exact_matches(concerts, favourites, ["Hip-Hop/Rap"])
    assert {i.concert.id for i in filtered} == {"rap", "both"}
    assert all(i.artist.name == "Contract Rapper" for i in filtered)


async def test_the_shelf_route_applies_the_search_genres() -> None:
    async with api_for(FakeAsyncRedis(), Fernet.generate_key().decode()) as api:
        await connect(api)
        response = await api.get(
            PREFIX + "/shelf",
            params={"place": "SF", "genre": "Not A Listed Genre", "time_zone": "UTC"},
        )
        assert response.status_code == 200
        assert response.json()["concerts"] == []


async def test_artists_reads_every_source_in_order_and_stops_paging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def artist(name: str, *, url: bool = True) -> dict[str, Any]:
        links = {"spotify": f"https://open.spotify.com/artist/{name}"} if url else {}
        return {"name": name, "external_urls": links}

    def spotify(request: httpx.Request) -> httpx.Response:
        path, params = request.url.path.removeprefix("/v1"), request.url.params
        calls.append(f"{path} {params}")
        if path == "/me/top/artists":
            return httpx.Response(200, json={"items": [artist("Top")]})
        if path == "/me/top/tracks":
            return httpx.Response(
                200, json={"items": [{"artists": [artist("Top"), artist("Song")]}]}
            )
        if path == "/me/following":
            if "after" in params:
                return httpx.Response(
                    200, json={"artists": {"items": [artist("Second")], "cursors": {"after": None}}}
                )
            return httpx.Response(
                200, json={"artists": {"items": [artist("First")], "cursors": {"after": "First"}}}
            )
        assert path == "/me/tracks"
        offset = int(params["offset"])
        items = [
            {"track": {"artists": [artist("Liked"), artist("Local", url=False)]}},
            {"track": None},
        ]
        return httpx.Response(200, json={"items": items, "next": "more" if offset == 0 else None})

    def client_for(base_url: str, params: dict[str, str]) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=base_url, params=params, transport=httpx.MockTransport(spotify)
        )

    monkeypatch.undo()
    monkeypatch.setattr("concert_scout.sources.http.make_client", client_for)
    found = await Client("id", "secret", "http://127.0.0.1:8000/cb").artists(TOKEN)
    assert [(a.name, a.source) for a in found] == [
        ("Top", "top"),
        ("Song", "track"),
        ("First", "followed"),
        ("Second", "followed"),
        ("Liked", "liked"),
    ]
    assert sum(c.startswith("/me/top/artists") for c in calls) == 3
    assert sum(c.startswith("/me/top/tracks") for c in calls) == 3
    assert sum(c.startswith("/me/tracks") for c in calls) == 2


async def test_liked_songs_stop_at_the_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    pages: list[str] = []

    def spotify(request: httpx.Request) -> httpx.Response:
        pages.append(request.url.params["offset"])
        return httpx.Response(200, json={"items": [], "next": "always more"})

    from concert_scout.sources.spotify import MAX_LIKED_PAGES, _liked  # pyright: ignore[reportPrivateUsage]

    async with httpx.AsyncClient(
        base_url="https://api.spotify.com/v1", transport=httpx.MockTransport(spotify)
    ) as client:
        assert await _liked(client, TOKEN) == []
    assert len(pages) == MAX_LIKED_PAGES == 20
    assert pages[-1] == "950"
