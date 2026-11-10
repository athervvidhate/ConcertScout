"""A corrected Reading reruns a Search without the interpreter, inside a typed Search's bounds."""

import datetime as dt
from collections.abc import AsyncIterator
from typing import Any, cast
from unittest.mock import AsyncMock

import httpx
import pytest

from concert_scout import pipeline, pool
from concert_scout.sources import geocoder
from tests.contracts import install_sources
from tests.test_app import TOKEN, api_for, parse_sse

PORTLAND_MAINE = "Portland, Maine, United States"
UKG = {"descriptors": ["UKG"], "tags": ["uk garage"], "genres": ["Dance/Electronic"]}


@pytest.fixture
async def api(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    install_sources(monkeypatch)
    monkeypatch.setattr(pipeline, "interpret", AsyncMock(side_effect=AssertionError("interpreter")))
    async with api_for() as client:
        yield client


async def rerun(api: httpx.AsyncClient, reading: dict[str, Any]) -> httpx.Response:
    return await api.post("/search", json={"reading": reading, "token": TOKEN, "time_zone": "UTC"})


async def test_a_corrected_place_reruns_the_search_without_the_interpreter(
    api: httpx.AsyncClient,
) -> None:
    response = await rerun(api, {**UKG, "place": PORTLAND_MAINE})
    events = parse_sse(response.text)
    data = dict(events)
    assert ("status", {"step": "interpret", "message": "Reading your Search"}) not in events
    assert data["reading"]["place"] == PORTLAND_MAINE
    cast(AsyncMock, geocoder.geocode).assert_called_once()
    assert cast(AsyncMock, geocoder.geocode).call_args.args[2] == PORTLAND_MAINE
    assert len(data["poster"]["recommendations"]) == 2
    assert "shareable" in data
    assert events[-1] == ("done", {})


async def test_a_corrected_place_gets_the_same_local_shorthand_as_typed_words(
    api: httpx.AsyncClient,
) -> None:
    response = await rerun(api, {**UKG, "place": "pdx"})
    assert dict(parse_sse(response.text))["reading"]["place"] == "Portland, Oregon, United States"


async def test_blank_dates_stay_blank(api: httpx.AsyncClient) -> None:
    await rerun(api, {**UKG, "place": PORTLAND_MAINE})
    args = cast(AsyncMock, pool.find_concerts).call_args.args
    assert (args[5], args[6]) == (None, None)


def too_far() -> str:
    return (dt.datetime.now(dt.UTC).date() + dt.timedelta(days=402)).isoformat()


@pytest.mark.parametrize(
    "body",
    [
        {"reading": {"artists": ["A"] * 21}},
        {"reading": {"artists": ["A" * 201]}},
        {"reading": {"genres": ["Polka"]}},
        {"reading": {"start": "2027-03-02", "end": "2027-03-01"}},
        {"reading": {"radius_miles": 50}},
        {"reading": {"place": "Boston", "region": "New England"}},
        {"reading": {"place": "Boston", "radius_miles": 501}},
        {"reading": {"place": "Boston", "end": "far"}},
        {"text": "UKG in SF", "reading": {"place": "Boston"}},
        {},
    ],
)
async def test_a_reading_is_held_to_the_bounds_of_a_typed_search(
    api: httpx.AsyncClient, body: dict[str, Any]
) -> None:
    if body.get("reading", {}).get("end") == "far":
        body = {"reading": {**body["reading"], "end": too_far()}}
    response = await api.post("/search", json={**body, "token": TOKEN, "time_zone": "UTC"})
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_search"
    cast(AsyncMock, geocoder.geocode).assert_not_called()
    cast(AsyncMock, pool.find_concerts).assert_not_called()
