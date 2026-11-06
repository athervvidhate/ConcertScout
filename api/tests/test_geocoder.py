import httpx
import pytest
from fakeredis import FakeAsyncRedis

from concert_scout.sources.geocoder import (
    GeocoderError,
    find_places,
    geocode,
    make_client,
    parse_places,
)
from concert_scout.sources.http import USER_AGENT
from tests.conftest import CHICAGO, geoapify_result


def test_parse_places_copies_each_result() -> None:
    assert parse_places({"results": [geoapify_result()]}) == [CHICAGO]


def test_no_results_means_no_place() -> None:
    assert parse_places({"results": []}) == []


async def test_geocode_asks_autocomplete_for_one_locality_and_identifies_the_app() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": [geoapify_result()]})

    async with make_client("test-key", httpx.MockTransport(handler)) as client:
        place = await geocode(client, FakeAsyncRedis(), "Chicago")

    assert place == CHICAGO
    request = requests[0]
    assert request.url.host == "api.geoapify.com"
    assert request.url.path == "/v1/geocode/autocomplete"
    assert dict(request.url.params) == {
        "apiKey": "test-key",
        "text": "Chicago",
        "type": "locality",
        "limit": "1",
        "format": "json",
    }
    assert request.headers["user-agent"] == USER_AGENT
    assert "@" not in request.headers["user-agent"]


async def test_a_repeat_place_comes_from_the_cache() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": [geoapify_result()]})

    redis = FakeAsyncRedis()
    async with make_client("test-key", httpx.MockTransport(handler)) as client:
        first = await geocode(client, redis, "Chicago")
        second = await geocode(client, redis, "  chicago ")

    assert first == second == CHICAGO
    assert len(requests) == 1


async def test_an_unknown_place_is_not_cached() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": []})

    redis = FakeAsyncRedis()
    async with make_client("test-key", httpx.MockTransport(handler)) as client:
        assert await geocode(client, redis, "Nowhere") is None
        assert await geocode(client, redis, "Nowhere") is None

    assert len(requests) == 2


async def test_geocode_reports_failures_without_the_api_key() -> None:
    async with make_client(
        "test-key", httpx.MockTransport(lambda _: httpx.Response(401))
    ) as client:
        with pytest.raises(GeocoderError) as caught:
            await geocode(client, FakeAsyncRedis(), "Chicago")

    assert "test-key" not in str(caught.value)
    assert caught.value.__cause__ is None


async def test_geocode_reports_an_unreadable_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [{"name": "Chicago"}]})

    async with make_client("test-key", httpx.MockTransport(handler)) as client:
        with pytest.raises(GeocoderError):
            await geocode(client, FakeAsyncRedis(), "Chicago")


async def test_find_places_asks_for_five_and_caches_them() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": [geoapify_result()]})

    redis = FakeAsyncRedis()
    async with make_client("test-key", httpx.MockTransport(handler)) as client:
        first = await find_places(client, redis, "Chi")
        second = await find_places(client, redis, "  chi ")

    assert first == second == [CHICAGO]
    assert len(requests) == 1
    assert requests[0].url.params["limit"] == "5"


async def test_city_aliases_share_the_expanded_place_cache() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": [geoapify_result()]})

    async with make_client("test-key", httpx.MockTransport(handler)) as client:
        redis = FakeAsyncRedis()
        await geocode(client, redis, "SF")
        await geocode(client, redis, "San Francisco, California, United States")
    assert len(requests) == 1
    assert requests[0].url.params["text"] == "San Francisco, California, United States"


def test_a_state_keeps_its_boundary_filter_and_a_city_does_not() -> None:
    state = {
        "formatted": "Texas, United States",
        "lat": 31.1,
        "lon": -99.1,
        "result_type": "state",
        "state_code": "TX",
        "country_code": "us",
    }
    place = parse_places({"results": [state]})[0]
    assert place.model_dump().get("state_code") == "TX"
    city = parse_places({"results": [state | {"result_type": "city"}]})[0]
    assert city.model_dump().get("state_code") is None
