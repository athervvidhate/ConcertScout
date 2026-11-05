import httpx
import pytest
from fakeredis import FakeAsyncRedis

from concert_scout.sources.geocoder import GeocoderError, geocode, make_client, parse_place
from concert_scout.sources.http import USER_AGENT
from tests.conftest import CHICAGO, geoapify_result


def test_parse_place_copies_the_top_result() -> None:
    assert parse_place({"results": [geoapify_result()]}) == CHICAGO


def test_no_results_means_no_place() -> None:
    assert parse_place({"results": []}) is None


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
