"""Taste import contracts: real routes and pipeline, with the import sources as typed seams."""

from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from fakeredis import FakeAsyncRedis
from pydantic import SecretStr

from concert_scout import pool
from concert_scout.sources import lastfm, listenbrainz
from tests.contracts import install_sources
from tests.test_app import TOKEN, api_for, parse_sse

USERNAME = "private-listener"
PLACE_ONLY = {"text": "place only in SF", "token": TOKEN, "time_zone": "UTC"}


@pytest.fixture(autouse=True)
def sources(monkeypatch: pytest.MonkeyPatch) -> None:
    install_sources(monkeypatch)


def reasons(stream: str) -> list[str]:
    poster: dict[str, Any] = dict(parse_sse(stream))["poster"]
    return [recommendation["reason"] for recommendation in poster["recommendations"]]


async def test_an_import_changes_a_poster() -> None:
    async with api_for() as api:
        without = await api.post("/search", json=PLACE_ONLY)
        imported = await api.post("/search", json={**PLACE_ONLY, "taste": ["Imported Artist"]})
    assert set(reasons(without.text)) == {"Coming up nearby"}
    assert set(reasons(imported.text)) == {"A source-backed match"}
    assert dict(parse_sse(imported.text))["interpreted"]["artists"] == ["Imported Artist"]
    lookups = cast(AsyncMock, pool.find_concerts).call_args.args[3]
    assert list(lookups) == ["Imported Artist"]


@pytest.mark.parametrize(
    ("source", "module", "error", "status", "code", "message"),
    [
        ("lastfm", lastfm, lastfm.UserNotFound, 404, "taste_user_not_found", "could not find"),
        ("lastfm", lastfm, lastfm.PrivateUser, 403, "taste_private", "hides its listening"),
        ("lastfm", lastfm, lastfm.LastfmError, 503, "taste_unavailable", "not answering"),
        (
            "listenbrainz",
            listenbrainz,
            listenbrainz.UserNotFound,
            404,
            "taste_user_not_found",
            "could not find",
        ),
        (
            "listenbrainz",
            listenbrainz,
            listenbrainz.ListenBrainzError,
            503,
            "taste_unavailable",
            "not answering",
        ),
    ],
)
async def test_a_failed_import_explains_itself(
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    module: Any,
    error: type[Exception],
    status: int,
    code: str,
    message: str,
) -> None:
    monkeypatch.setattr(module, "top_artists", AsyncMock(side_effect=error("private detail")))
    async with api_for(lastfm_key=SecretStr("unused-test-key")) as api:
        response = await api.post(f"/taste/{source}", json={"username": USERNAME})
    assert response.status_code == status
    body = response.json()
    assert body["code"] == code and message in body["message"]
    assert "private detail" not in response.text and USERNAME not in response.text


async def test_the_server_keeps_nothing_about_who_imported() -> None:
    top_artists = AsyncMock(return_value=["Imported Artist"])
    redis = FakeAsyncRedis()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(listenbrainz, "top_artists", top_artists)
        async with api_for(redis) as api:
            imported = await api.post("/taste/listenbrainz", json={"username": USERNAME})
            taste = imported.json()["artists"]
            await api.post("/search", json={**PLACE_ONLY, "taste": taste})
    assert taste == ["Imported Artist"]
    keys = cast(list[bytes], await redis.keys("*"))  # pyright: ignore[reportUnknownMemberType]
    values = [await redis.dump(key) for key in keys]
    assert not any(USERNAME.encode() in (entry or b"") for entry in [*keys, *values])
