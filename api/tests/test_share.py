"""A Shared Poster is promoted from what the server produced, never built from the browser."""

import datetime as dt
from typing import Any, cast

import httpx
import pytest
from fakeredis import FakeAsyncRedis

from concert_scout import limits, share
from concert_scout.models import Recommendation
from tests.contracts import CONCERTS, DAY, install_sources
from tests.test_app import TOKEN, api_for, parse_sse


@pytest.fixture(autouse=True)
def domain_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    install_sources(monkeypatch)


async def stored_under(redis: FakeAsyncRedis, pattern: str) -> dict[str, str]:
    """Every record whose key matches, as text."""
    keys = cast(list[bytes], await redis.keys(pattern))  # pyright: ignore[reportUnknownMemberType]
    return {key.decode(): str(await redis.get(key)) for key in keys}


async def finished_search(api: httpx.AsyncClient, text: str = "UKG in SF", **body: Any) -> Any:
    response = await api.post(
        "/search", json={"text": text, "token": TOKEN, "time_zone": "UTC", **body}
    )
    return dict(parse_sse(response.text))


async def test_a_finished_search_shares_the_poster_the_server_produced() -> None:
    async with api_for() as api:
        events = await finished_search(api)
        shared = await api.post("/share", json={"search_id": events["shareable"]["search_id"]})
        assert shared.status_code == 200
        opened = await api.get(f"/share/{shared.json()['id']}")
    assert opened.status_code == 200
    body = opened.json()
    assert body["recommendations"] == events["poster"]["recommendations"]
    assert body["interpreted"]["place"] == events["interpreted"]["place"]
    assert body["made"] == dt.datetime.now(dt.UTC).date().isoformat()


async def test_sharing_a_search_again_gives_the_same_link_and_changes_nothing() -> None:
    redis = FakeAsyncRedis()
    async with api_for(redis) as api:
        search_id = (await finished_search(api))["shareable"]["search_id"]
        first = (await api.post("/share", json={"search_id": search_id})).json()["id"]
        stored = await redis.get(f"share:poster:{first}")
        # Even a record swapped under the Search ID cannot replace the Poster already shared.
        swapped = share.Made(made=DAY, interpreted=None, recommendations=[])
        await redis.set(f"share:search:{search_id}", swapped.model_dump_json())
        second = (await api.post("/share", json={"search_id": search_id})).json()["id"]
    assert first == second and len(first) == 12
    assert await redis.get(f"share:poster:{first}") == stored


async def test_records_expire() -> None:
    redis = FakeAsyncRedis()
    async with api_for(redis) as api:
        search_id = (await finished_search(api))["shareable"]["search_id"]
        link = (await api.post("/share", json={"search_id": search_id})).json()["id"]
    assert 0 < await redis.ttl(f"share:search:{search_id}") <= 6 * 3600
    assert 89 * 86400 < await redis.ttl(f"share:poster:{link}") <= 90 * 86400


async def test_the_browser_cannot_forge_a_poster() -> None:
    redis = FakeAsyncRedis()
    forged = [
        {"search_id": "x" * 22, "recommendations": [{"reason": "forged"}]},
        {"recommendations": [{"reason": "forged"}]},
        {"search_id": "../../examples"},
        {"search_id": "a b"},
    ]
    async with api_for(redis) as api:
        real = (await finished_search(api))["shareable"]["search_id"]
        for body in forged:
            denied = await api.post("/share", json=body)
            assert denied.status_code == 422 and denied.json()["code"] == "invalid_share"
        with_poster = await api.post(
            "/share", json={"search_id": real, "recommendations": [{"reason": "forged"}]}
        )
        # An ID the server never issued has nothing to promote.
        unknown = await api.post("/share", json={"search_id": "A" * 22})
    assert with_poster.status_code == 422
    assert unknown.status_code == 404 and unknown.json()["code"] == "search_expired"
    assert await stored_under(redis, "share:poster:*") == {}


async def test_an_expired_search_cannot_be_shared() -> None:
    redis = FakeAsyncRedis()
    async with api_for(redis) as api:
        search_id = (await finished_search(api))["shareable"]["search_id"]
        await redis.delete(f"share:search:{search_id}")
        expired = await api.post("/share", json={"search_id": search_id})
    assert expired.status_code == 404 and expired.json()["code"] == "search_expired"


async def test_an_unknown_or_malformed_link_is_refused() -> None:
    async with api_for() as api:
        unknown = await api.get("/share/AAAAAAAAAAAA")
        malformed = await api.get("/share/not-a-link")
    assert unknown.status_code == 404 and unknown.json()["code"] == "share_not_found"
    assert malformed.status_code == 422


async def test_concerts_that_have_passed_are_dropped_when_read() -> None:
    redis = FakeAsyncRedis()
    yesterday = dt.datetime.now(dt.UTC).date() - dt.timedelta(days=1)
    over = CONCERTS[0].model_copy(update={"date": yesterday})
    over_also = CONCERTS[1].model_copy(update={"date": yesterday})
    made = share.Made(
        made=yesterday,
        interpreted=None,
        recommendations=[
            Recommendation(concert=over, reason="Over"),
            Recommendation(concert=CONCERTS[2], reason="Fits", also=[over_also, CONCERTS[0]]),
        ],
    )
    search_id = await share.keep(redis, made)
    async with api_for(redis) as api:
        link = (await api.post("/share", json={"search_id": search_id})).json()["id"]
        picks = (await api.get(f"/share/{link}")).json()["recommendations"]
    assert [p["concert"]["id"] for p in picks] == ["contract-three"]
    assert [c["id"] for c in picks[0]["also"]] == ["contract-one"]


async def test_a_shared_poster_holds_no_coordinates_or_imported_taste() -> None:
    redis = FakeAsyncRedis()
    near = {"lat": 32.712345, "lon": -117.198765}
    async with api_for(redis) as api:
        # The Search names no Artist, so the imported Taste becomes its seed Artists.
        events = await finished_search(
            api, "place only SF", taste=["Private Imported Artist"], near=near
        )
        assert events["interpreted"]["artists"] == ["Private Imported Artist"]
        search_id = events["shareable"]["search_id"]
        link = (await api.post("/share", json={"search_id": search_id})).json()["id"]
        body = (await api.get(f"/share/{link}")).json()
    assert body["interpreted"]["artists"] == []
    for stored in (await stored_under(redis, "share:*")).values():
        assert "Private Imported Artist" not in stored
        assert "32.7123" not in stored and "117.1987" not in stored


async def test_a_poster_with_no_picks_cannot_be_shared() -> None:
    async with api_for() as api:
        events = await finished_search(api, "empty in SF")
    assert events["poster"]["recommendations"] == []
    assert "shareable" not in events


async def test_sharing_is_limited_per_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limits, "SHARES_PER_HOUR", 2)
    async with api_for(client_ip_header="x-real-ip") as api:
        search_id = (await finished_search(api))["shareable"]["search_id"]
        body = {"search_id": search_id}
        first = {"x-real-ip": "1.1.1.1"}
        for _ in range(2):
            assert (await api.post("/share", json=body, headers=first)).status_code == 200
        denied = await api.post("/share", json=body, headers=first)
        other = await api.post("/share", json=body, headers={"x-real-ip": "2.2.2.2"})
    assert denied.status_code == 429 and denied.json()["retry_after"] > 0
    assert other.status_code == 200
