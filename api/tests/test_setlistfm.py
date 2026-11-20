import datetime as dt
from collections.abc import Sequence
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from pydantic import SecretStr

from concert_scout import limits
from concert_scout.app import create_app
from concert_scout.sources import http, setlistfm
from tests.contracts import contract_model, forbidden_http, install_sources, settings_with

KHRUANGBIN_MBID = "83d91898-7763-47d7-b03b-b92132375c47"
ARTIST_URL = "https://www.setlist.fm/setlists/khruangbin-23da00bb.html"
TODAY = dt.date(2026, 11, 20)


def _setlist(
    date: str,
    main_songs: Sequence[str | dict[str, Any]],
    *,
    encore_songs: Sequence[str | dict[str, Any]] | None = None,
    artist_name: str = "Khruangbin",
    artist_mbid: str = KHRUANGBIN_MBID,
    artist_url: str | None = ARTIST_URL,
    venue: str | None = "Greek Theatre",
    city: dict[str, Any] | None = None,
    setlist_url: str | None = "https://www.setlist.fm/setlist/khruangbin/2026/show.html",
) -> dict[str, Any]:
    def song_obj(entry: str | dict[str, Any]) -> dict[str, Any]:
        return {"name": entry} if isinstance(entry, str) else entry

    sets: list[dict[str, Any]] = [{"song": [song_obj(s) for s in main_songs]}]
    if encore_songs is not None:
        sets.append({"encore": 1, "song": [song_obj(s) for s in encore_songs]})
    venue_obj: dict[str, Any] = {}
    if venue is not None:
        venue_obj["name"] = venue
    if city is not None:
        venue_obj["city"] = city
    artist_obj: dict[str, Any] = {"name": artist_name, "mbid": artist_mbid}
    if artist_url is not None:
        artist_obj["url"] = artist_url
    record: dict[str, Any] = {
        "eventDate": date,
        "artist": artist_obj,
        "venue": venue_obj,
        "sets": {"set": sets},
    }
    if setlist_url is not None:
        record["url"] = setlist_url
    return record


BERKELEY = {
    "name": "Berkeley",
    "stateCode": "CA",
    "country": {"code": "US", "name": "United States"},
}
LONDON = {
    "name": "London",
    "stateCode": "ENG",
    "country": {"code": "GB", "name": "United Kingdom"},
}


def _five_shows_payload() -> dict[str, Any]:
    staples = [
        "Fifteen Fifty-Three",
        "May Ninth",
        "August 10",
        "Evan Finds the Third Room",
        "Time (You and I)",
        "Maria También",
        "A Love International",
        "Hold Me Up (Thank You)",
        "So We Won't Forget",
    ]
    return {
        "setlist": [
            # Upcoming show in the future — must be ignored.
            _setlist("25-12-2026", staples[:5], city=BERKELEY),
            # Incomplete show (< 3 live songs; tape tracks do not count) — must be ignored.
            _setlist(
                "01-11-2026",
                ["May Ninth", {"name": "Walk-On Tape", "tape": True}, "August 10"],
                city=BERKELEY,
            ),
            # 5 recent completed shows (newest first), plus a 6th older show that stays out.
            _setlist(
                "24-10-2026",
                [*staples[:8], "May Ninth", {"name": "Outro Tape", "tape": True}],
                encore_songs=["People Everywhere (Still Alive)"],
                venue="Greek Theatre",
                city=BERKELEY,
            ),
            _setlist(
                "20-10-2026",
                staples[:7],
                encore_songs=["People Everywhere (Still Alive)"],
                venue="Red Rocks Amphitheatre",
                city={
                    "name": "Morrison",
                    "stateCode": "CO",
                    "country": {"code": "US", "name": "United States"},
                },
            ),
            _setlist(
                "16-10-2026",
                staples[:6],
                encore_songs=["People Everywhere (Still Alive)"],
                venue="Eventim Apollo",
                city=LONDON,
            ),
            _setlist(
                "12-10-2026",
                staples[:6],
                encore_songs=["People Everywhere (Still Alive)"],
                venue="Radio City Music Hall",
                city=BERKELEY,
            ),
            _setlist(
                "08-10-2026",
                staples[:5],
                venue="The Fillmore",
                city=BERKELEY,
            ),
            # 6th completed show — outside the last 5 window.
            _setlist(
                "01-09-2026",
                ["Old Tour Only", "Another Old Song", "Third Old Song"],
                city=BERKELEY,
            ),
        ]
    }


def test_parse_setlists_computes_last_five_shows_staples_and_encores() -> None:
    summary = setlistfm.parse_setlists(
        "Khruangbin", _five_shows_payload(), mbid=KHRUANGBIN_MBID, today=TODAY
    )

    assert summary.artist == "Khruangbin"
    assert summary.mbid == KHRUANGBIN_MBID
    assert summary.show_count == 5
    # Song counts across last 5 shows: (9+1)=10, (7+1)=8, (6+1)=7, (6+1)=7, 5 -> mean 7.4 -> 7
    assert summary.average_songs == 7
    assert summary.encore_shows == 4
    assert summary.last_show == setlistfm.SetlistShow(
        date=dt.date(2026, 10, 24), venue="Greek Theatre", city="Berkeley, CA"
    )
    assert summary.source_url == ARTIST_URL
    assert len(summary.staples) == setlistfm.MAX_STAPLES
    by_name = {s.name: s for s in summary.staples}
    # Reprise in the same show still counts as 1 show (5 of 5, not 6 of 5).
    assert by_name["May Ninth"].shows == 5
    assert by_name["May Ninth"].encore_shows == 0
    assert by_name["People Everywhere (Still Alive)"].shows == 4
    assert by_name["People Everywhere (Still Alive)"].encore_shows == 4
    assert "Walk-On Tape" not in by_name
    assert "Outro Tape" not in by_name
    assert "Old Tour Only" not in by_name


def test_parse_setlists_formats_non_us_city_and_omits_missing_fields() -> None:
    payload = {
        "setlist": [
            _setlist(
                "16-10-2026",
                ["Song A", "Song B", "Song C"],
                venue=None,
                city=LONDON,
                artist_url="javascript:alert(1)",
                setlist_url="http://www.setlist.fm/setlist/test/2026/london.html",
            )
        ]
    }
    summary = setlistfm.parse_setlists("Khruangbin", payload, today=TODAY)
    assert summary.show_count == 1
    assert summary.average_songs == 3
    assert summary.encore_shows == 0
    assert summary.last_show == setlistfm.SetlistShow(
        date=dt.date(2026, 10, 16), venue=None, city="London, United Kingdom"
    )
    # Unsafe artist URL rejected; valid http setlist.fm URL normalized to https.
    assert summary.source_url == "https://www.setlist.fm/setlist/test/2026/london.html"


def test_exact_name_mode_rejects_partial_matches_and_other_namesakes() -> None:
    other_mbid = "11111111-1111-1111-1111-111111111111"
    payload = {
        "setlist": [
            # Substring collab — must be ignored.
            _setlist(
                "25-10-2026",
                ["Texas Sun", "Midnight", "C-Side"],
                artist_name="Khruangbin & Leon Bridges",
                artist_mbid="22222222-2222-2222-2222-222222222222",
                city=BERKELEY,
            ),
            # Exact match (pins MBID to KHRUANGBIN_MBID).
            _setlist(
                "24-10-2026",
                ["May Ninth", "August 10", "Time (You and I)"],
                artist_name="Khruangbin",
                artist_mbid=KHRUANGBIN_MBID,
                city=BERKELEY,
            ),
            # Different artist sharing exact normalized name — must not blend in.
            _setlist(
                "20-10-2026",
                ["Wrong Band 1", "Wrong Band 2", "Wrong Band 3"],
                artist_name="The Khruangbin",
                artist_mbid=other_mbid,
                city=BERKELEY,
            ),
        ]
    }
    summary = setlistfm.parse_setlists("Khruangbin", payload, exact_name=True, today=TODAY)
    assert summary.show_count == 1
    assert summary.mbid == KHRUANGBIN_MBID
    assert [s.name for s in summary.staples] == ["May Ninth", "August 10", "Time (You and I)"]


def test_no_completed_shows_produces_empty_summary_with_no_invented_values() -> None:
    payload = {"setlist": [_setlist("24-10-2026", ["Only One", "Only Two"])]}
    summary = setlistfm.parse_setlists("Nobody", payload, today=TODAY)
    assert summary.show_count == 0
    assert summary.average_songs is None
    assert summary.last_show is None
    assert summary.staples == []
    assert summary.source_url is None


async def test_artist_setlist_queries_by_mbid_and_caches_for_seven_days() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_five_shows_payload())

    redis = FakeAsyncRedis()
    async with setlistfm.make_client("secret-setlist-key", httpx.MockTransport(handler)) as client:
        first = await setlistfm.artist_setlist(client, redis, "Khruangbin", mbid=KHRUANGBIN_MBID)
        second = await setlistfm.artist_setlist(client, redis, "Khruangbin", mbid=KHRUANGBIN_MBID)

    assert len(seen) == 1
    assert seen[0].url.path == f"/rest/1.0/artist/{KHRUANGBIN_MBID}/setlists"
    assert seen[0].url.params["p"] == "1"
    assert seen[0].headers["x-api-key"] == "secret-setlist-key"
    assert seen[0].headers["accept"] == "application/json"
    assert seen[0].headers["user-agent"] == http.USER_AGENT
    assert "@" not in seen[0].headers["user-agent"]
    assert first == second
    ttl = await redis.ttl(f"setlist:mbid:{KHRUANGBIN_MBID}")
    assert 6 * 86400 < ttl <= 7 * 86400


async def test_artist_setlist_falls_back_to_exact_name_when_mbid_missing_or_invalid() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_five_shows_payload())

    redis = FakeAsyncRedis()
    async with setlistfm.make_client("secret-key", httpx.MockTransport(handler)) as client:
        # Malformed/non-UUID mbid never touches /artist/{mbid}/setlists (no path traversal).
        summary = await setlistfm.artist_setlist(
            client, redis, "Khruangbin", mbid="../../etc/passwd"
        )

    assert len(seen) == 1
    assert seen[0].url.path == "/rest/1.0/search/setlists"
    assert seen[0].url.params["artistName"] == "Khruangbin"
    assert seen[0].url.params["p"] == "1"
    assert summary.show_count == 5


async def test_404_caches_empty_summary_and_server_errors_never_leak_key() -> None:
    calls = 0

    def not_found(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(404, json={"code": 404, "message": "not found"})

    redis = FakeAsyncRedis()
    async with setlistfm.make_client("secret-key", httpx.MockTransport(not_found)) as client:
        first = await setlistfm.artist_setlist(client, redis, "Unknown Artist")
        second = await setlistfm.artist_setlist(client, redis, "Unknown Artist")
    assert calls == 1
    assert first.show_count == 0 and second.show_count == 0

    def failed(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="overloaded")

    async with setlistfm.make_client("super-secret-value", httpx.MockTransport(failed)) as client:
        with pytest.raises(setlistfm.SetlistfmError) as caught:
            await setlistfm.artist_setlist(client, FakeAsyncRedis(), "Flaky Artist")
    assert "super-secret-value" not in str(caught.value)
    assert "503" in str(caught.value)


async def test_artist_setlist_route_contracts_and_never_called_during_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_sources(monkeypatch)
    # Without SETLISTFM_API_KEY configured, route succeeds cleanly with empty summary and no HTTP.
    app_unconfigured = create_app(
        settings_with(),
        httpx.MockTransport(forbidden_http),
        FakeAsyncRedis(),
        contract_model(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app_unconfigured), base_url="http://test"
    ) as client:
        empty = await client.get("/artist/setlist", params={"name": "Khruangbin"})
        invalid = await client.get("/artist/setlist")
    assert empty.status_code == 200
    assert empty.json() == {
        "artist": "Khruangbin",
        "show_count": 0,
        "encore_shows": 0,
        "staples": [],
    }
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "invalid_artist"

    # With SETLISTFM_API_KEY configured, route returns parsed summary and /search never calls it.
    expected = setlistfm.parse_setlists(
        "Khruangbin", _five_shows_payload(), mbid=KHRUANGBIN_MBID, today=TODAY
    )
    spy = AsyncMock(return_value=expected)
    monkeypatch.setattr(setlistfm, "artist_setlist", spy)
    app = create_app(
        settings_with(setlistfm_api_key=SecretStr("configured-key")),
        httpx.MockTransport(forbidden_http),
        FakeAsyncRedis(),
        contract_model(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        search_res = await client.post(
            "/search", json={"text": "UKG in SF", "token": "test-token", "time_zone": "UTC"}
        )
        assert search_res.status_code == 200
        spy.assert_not_awaited()

        res = await client.get(
            "/artist/setlist", params={"name": "Khruangbin", "mbid": KHRUANGBIN_MBID}
        )
    assert res.status_code == 200
    body = res.json()
    assert body["artist"] == "Khruangbin"
    assert body["show_count"] == 5
    assert body["average_songs"] == 7
    assert body["source_url"] == ARTIST_URL
    spy.assert_awaited_once()


async def test_artist_setlist_route_rate_limits_visitors_and_survives_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_sources(monkeypatch)
    monkeypatch.setattr(limits, "ARTIST_PER_HOUR", 2)
    monkeypatch.setattr(
        setlistfm, "artist_setlist", AsyncMock(side_effect=setlistfm.SetlistfmError("status 503"))
    )
    app = create_app(
        settings_with(setlistfm_api_key=SecretStr("configured-key")),
        httpx.MockTransport(forbidden_http),
        FakeAsyncRedis(),
        contract_model(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        first = await client.get("/artist/setlist", params={"name": "Khruangbin"})
        second = await client.get("/artist/setlist", params={"name": "Khruangbin"})
        limited = await client.get("/artist/setlist", params={"name": "Khruangbin"})

    assert first.status_code == 200 and first.json()["show_count"] == 0
    assert second.status_code == 200
    assert limited.status_code == 429 and limited.json()["code"] == "visitor_limit"
