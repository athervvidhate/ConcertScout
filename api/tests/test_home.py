"""Public home reads cached facts without calling a provider or model."""

import datetime as dt
from unittest.mock import AsyncMock

import httpx
import pytest
from fakeredis import FakeAsyncRedis

from concert_scout import cache, home, limits
from concert_scout.app import create_app, make_services
from concert_scout.models import Poster, Recommendation
from tests.contracts import (
    CONCERTS,
    DAY,
    contract_model,
    forbidden_http,
    install_sources,
    settings_with,
)


async def test_public_examples_read_only_even_on_a_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    build = AsyncMock(side_effect=AssertionError("Public home cannot run a Search"))
    monkeypatch.setattr(home, "run_search", build)
    redis = FakeAsyncRedis()
    app = create_app(settings_with(), httpx.MockTransport(forbidden_http), redis, contract_model())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as api:
        assert (await api.get("/examples")).json() == {"examples": []}
        example = home.Example(
            text=home.EXAMPLES[0],
            poster=Poster(recommendations=[Recommendation(concert=CONCERTS[0], reason="Fits")]),
        )
        await cache.write(redis, home.KEY, home.Examples(examples=[example]), home.TTL)
        response = await api.get("/examples")
        assert response.status_code == 200
        kept = response.json()["examples"][0]["poster"]["recommendations"][0]
        assert kept["concert"]["url"] == CONCERTS[0].url
        assert kept["concert"]["venue"] == CONCERTS[0].venue
    build.assert_not_called()


async def test_expired_source_dates_stay_out() -> None:
    redis = FakeAsyncRedis()
    expired = CONCERTS[0].model_copy(update={"date": DAY - dt.timedelta(days=1)})
    pick = Recommendation(concert=expired, reason="Fits", also=[CONCERTS[1]])
    await cache.write(
        redis,
        home.KEY,
        home.Examples(
            examples=[home.Example(text="Search", poster=Poster(recommendations=[pick]))]
        ),
        home.TTL,
    )
    assert (await home.read(redis, DAY)).examples[0].poster.recommendations == []


async def test_nightly_refresh_builds_pipeline_posters(monkeypatch: pytest.MonkeyPatch) -> None:
    install_sources(monkeypatch)
    monkeypatch.setattr(home, "EXAMPLES", ("UKG in SF",))
    redis = FakeAsyncRedis()
    services = make_services(
        settings_with(), httpx.MockTransport(forbidden_http), redis, contract_model()
    )
    await home.refresh(services)
    stored = await home.read(redis, DAY)
    assert len(stored.examples) == 1
    assert stored.examples[0].candidates
    assert stored.examples[0].poster.recommendations[0].concert.id == "contract-one"
    assert await redis.ttl(home.KEY) > 0


async def test_refresh_respects_shared_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    guard = AsyncMock(side_effect=limits.SpendCapReached(60))
    monkeypatch.setattr(limits, "check_spend", guard)
    redis = FakeAsyncRedis()
    services = make_services(
        settings_with(), httpx.MockTransport(forbidden_http), redis, contract_model()
    )
    await home.refresh(services)
    assert await redis.get(home.KEY) is None
    assert guard.await_count == 1
