"""Cache warming: it fills the keys a Search reads, and only the scheduler can start it."""

from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fakeredis import FakeAsyncRedis

from concert_scout import home, pool, sync, warm
from concert_scout.app import create_app, make_services
from concert_scout.sources import geocoder, listenbrainz, ticketmaster
from tests.contracts import (
    DAY,
    NOW,
    PLACE,
    contract_model,
    forbidden_http,
    idle_musicbrainz,
    install_sources,
    settings_with,
)


def ticketmaster_and_listenbrainz(request: httpx.Request) -> httpx.Response:
    if request.url.host == "app.ticketmaster.com":
        event: dict[str, Any] = {
            "id": "warm-one",
            "name": "Warm Show",
            "url": "https://tickets.example/warm",
            "dates": {"start": {"localDate": f"{DAY}"}},
            "_embedded": {
                "attractions": [
                    {"name": "Warm Artist", "externalLinks": {"musicbrainz": [{"id": "warm-mbid"}]}}
                ]
            },
        }
        body = {"page": {"totalElements": 1}, "_embedded": {"events": [event]}}
        return httpx.Response(200, json=body)
    if request.url.host == "api.listenbrainz.org":
        body = [{"artist_mbid": "warm-mbid", "tag": {"artist": [{"tag": "shoegaze"}]}}]
        return httpx.Response(200, json=body)
    return forbidden_http(request)


async def test_warming_fills_the_pool_and_tags_a_later_search_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(warm, "PLACES", ("San Francisco, California, United States",))
    monkeypatch.setattr(geocoder, "geocode", AsyncMock(return_value=PLACE))
    redis = FakeAsyncRedis()
    services = make_services(
        settings_with(), httpx.MockTransport(ticketmaster_and_listenbrainz), redis
    )
    [warmed] = await warm.warm(services, NOW)
    assert (warmed.concerts, warmed.artists, warmed.error) == (1, 1, None)

    # A Search afterwards may not reach either source: everything it needs is cached.
    async with ticketmaster.make_client("unused", httpx.MockTransport(forbidden_http)) as tm:
        concerts = await pool.find_concerts(
            tm, idle_musicbrainz(), redis, PLACE, [], None, None, NOW
        )
    async with listenbrainz.make_client(httpx.MockTransport(forbidden_http)) as lb:
        tags = listenbrainz.TagFetch(lb, redis)
        tags.add(concerts)
        assert await tags.tags() == {"warm-mbid": ["shoegaze"]}
    assert [c.id for c in concerts] == ["warm-one"]


async def test_one_failing_place_does_not_stop_the_others(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(warm, "PLACES", ("Nowhere", "San Francisco"))
    monkeypatch.setattr(
        geocoder, "geocode", AsyncMock(side_effect=[geocoder.GeocoderError("down"), PLACE])
    )
    services = make_services(
        settings_with(), httpx.MockTransport(ticketmaster_and_listenbrainz), FakeAsyncRedis()
    )
    nowhere, san_francisco = await warm.warm(services, NOW)
    assert nowhere.error == "down"
    assert san_francisco.concerts == 1


def api_for(**settings: Any) -> httpx.AsyncClient:
    app = create_app(
        settings_with(**settings),
        httpx.MockTransport(forbidden_http),
        FakeAsyncRedis(),
        contract_model(),
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test")


@pytest.mark.parametrize("path", ["/warm", "/refresh-examples", "/sync"])
async def test_without_a_secret_there_are_no_scheduler_routes(path: str) -> None:
    async with api_for() as api:
        assert (await api.get(path)).status_code == 404


async def test_only_the_scheduler_secret_starts_a_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    ran = AsyncMock(return_value=[])
    monkeypatch.setattr(sync, "run", ran)
    async with api_for(cron_secret="right-secret") as api:
        for headers in ({}, {"Authorization": "Bearer wrong"}):
            refused = await api.get("/sync", headers=headers)
            assert refused.status_code == 401
            assert refused.json()["code"] == "not_scheduler"
        assert ran.await_count == 0
        right = await api.get("/sync", headers={"Authorization": "Bearer right-secret"})
    assert right.json() == []
    ran.assert_awaited_once()


async def test_only_the_scheduler_secret_starts_warming(monkeypatch: pytest.MonkeyPatch) -> None:
    install_sources(monkeypatch)
    ran = AsyncMock(return_value=[warm.Warmed("Somewhere", 2, 1, 0.1)])
    monkeypatch.setattr(warm, "warm", ran)
    async with api_for(cron_secret="right-secret") as api:
        assert (await api.get("/warm")).status_code == 401
        wrong = await api.get("/warm", headers={"Authorization": "Bearer wrong"})
        assert wrong.status_code == 401
        assert ran.await_count == 0

        right = await api.get("/warm", headers={"Authorization": "Bearer right-secret"})
    assert right.status_code == 200
    assert right.json()[0] == {
        "place": "Somewhere",
        "concerts": 2,
        "artists": 1,
        "seconds": 0.1,
        "error": None,
    }
    ran.assert_awaited_once()


async def test_only_the_scheduler_secret_refreshes_examples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ran = AsyncMock()
    monkeypatch.setattr(home, "refresh", ran)
    async with api_for(cron_secret="right-secret") as api:
        refused = await api.get("/refresh-examples", headers={"Authorization": "Bearer wrong"})
        assert refused.status_code == 401
        assert ran.await_count == 0
        right = await api.get("/refresh-examples", headers={"Authorization": "Bearer right-secret"})
    assert right.status_code == 200
    ran.assert_awaited_once()
