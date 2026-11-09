"""Every spelling of a city lands on one point, so Searches there share one cached pool."""

from typing import Any

import httpx
from fakeredis import FakeAsyncRedis

from concert_scout.sources import geocoder


def city(lat: float, county: str | None = None, importance: float | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "result_type": "city",
        "city": "New York",
        "state": "New York",
        "state_code": "NY",
        "country": "United States",
        "country_code": "us",
        "county": county,
        "formatted": f"New York, NY ({county or 'city'})",
        "lat": lat,
        "lon": -74.0,
        "rank": {"confidence": 1, "importance": importance},
    }
    return record


def geoapify(answers: dict[str, list[dict[str, Any]]], asked: list[str]) -> httpx.MockTransport:
    def respond(request: httpx.Request) -> httpx.Response:
        text = request.url.params["text"]
        asked.append(text)
        return httpx.Response(200, json={"results": answers.get(text, [])})

    return httpx.MockTransport(respond)


async def test_a_short_spelling_snaps_to_the_city_most_people_mean() -> None:
    asked: list[str] = []
    answers = {
        "New York, NY": [city(40.68, county="Kings County")],
        "New York, New York, United States": [city(40.71, importance=0.88)],
    }
    redis = FakeAsyncRedis()
    async with geocoder.make_client("unused", geoapify(answers, asked)) as client:
        place = await geocoder.geocode(client, redis, "New York, NY")
        again = await geocoder.geocode(client, redis, "New York, NY")
    assert place and again
    assert (place.lat, again.lat) == (40.71, 40.71)
    assert asked == ["New York, NY", "New York, New York, United States"]


async def test_the_full_name_itself_needs_no_second_lookup() -> None:
    asked: list[str] = []
    answers = {"New York, New York, United States": [city(40.71, importance=0.88)]}
    async with geocoder.make_client("unused", geoapify(answers, asked)) as client:
        place = await geocoder.geocode(
            client, FakeAsyncRedis(), "New York, New York, United States"
        )
    assert place and place.lat == 40.71
    assert asked == ["New York, New York, United States"]


async def test_a_different_city_under_the_full_name_does_not_move_the_place() -> None:
    asked: list[str] = []
    elsewhere = city(43.1) | {"city": "New York Mills"}
    answers = {
        "New York, NY": [city(40.68, county="Kings County")],
        "New York, New York, United States": [elsewhere],
    }
    async with geocoder.make_client("unused", geoapify(answers, asked)) as client:
        place = await geocoder.geocode(client, FakeAsyncRedis(), "New York, NY")
    assert place and place.lat == 40.68


async def test_a_failed_second_lookup_keeps_the_first_answer() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.params["text"] == "New York, NY":
            return httpx.Response(200, json={"results": [city(40.68, county="Kings County")]})
        return httpx.Response(503)

    async with geocoder.make_client("unused", httpx.MockTransport(respond)) as client:
        place = await geocoder.geocode(client, FakeAsyncRedis(), "New York, NY")
    assert place and place.lat == 40.68
