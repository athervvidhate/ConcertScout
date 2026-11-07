import datetime as dt
from typing import Any

import httpx
import pytest

from concert_scout.models import Price
from concert_scout.sources import ticketmaster
from concert_scout.sources.ticketmaster import (
    TicketmasterError,
    find_concerts,
    make_client,
    parse_concert,
    parse_concerts,
)
from tests.conftest import tm_body, tm_record


def with_start(**start: Any) -> dict[str, Any]:
    record = tm_record()
    record["dates"]["start"] |= start
    return record


def test_parse_concert_copies_facts_from_the_record() -> None:
    concert = parse_concert(tm_record())

    assert concert.id == "vvG18Z_ueUZbii"
    assert concert.name == "Khruangbin: The Ether Tour"
    assert concert.url == "https://www.ticketmaster.com/event/040064D0B6018B2C"
    assert concert.artists == ["Khruangbin", "Men I Trust"]
    assert concert.date == dt.date(2026, 11, 20)
    assert concert.time == dt.time(19, 30)
    assert concert.venue == "The Salt Shed"
    assert concert.city == "Chicago"
    assert concert.region == "IL"
    assert concert.price == Price(min=45.5, max=120.0, currency="USD")


@pytest.mark.parametrize(
    "start",
    [{"timeTBA": True}, {"noSpecificTime": True}],
)
def test_a_time_flagged_unknown_is_left_out(start: dict[str, Any]) -> None:
    assert parse_concert(with_start(**start)).time is None


def test_a_record_without_a_time_is_left_out() -> None:
    record = tm_record()
    del record["dates"]["start"]["localTime"]

    assert parse_concert(record).time is None


@pytest.mark.parametrize("start", [{"dateTBA": True}, {"dateTBD": True}])
def test_a_date_flagged_unknown_is_left_out(start: dict[str, Any]) -> None:
    assert parse_concert(with_start(**start)).date is None


def test_a_record_without_price_ranges_has_no_price() -> None:
    record = tm_record()
    del record["priceRanges"]

    assert parse_concert(record).price is None


def test_a_zero_price_range_counts_as_missing() -> None:
    zero = {"type": "standard", "currency": "USD", "min": 0.0, "max": 0.0}

    assert parse_concert(tm_record(priceRanges=[zero])).price is None


def test_a_record_without_attractions_or_venue_keeps_its_other_facts() -> None:
    concert = parse_concert(tm_record(_embedded={}))

    assert concert.artists == []
    assert concert.venue is None
    assert concert.city is None
    assert concert.region is None
    assert concert.name == "Khruangbin: The Ether Tour"


def test_cancelled_concerts_are_dropped() -> None:
    cancelled = tm_record(id="gone")
    cancelled["dates"]["status"]["code"] = "cancelled"

    concerts = parse_concerts(tm_body(cancelled, tm_record()))

    assert [concert.id for concert in concerts] == ["vvG18Z_ueUZbii"]


def test_a_city_with_no_listings_has_no_concerts() -> None:
    assert parse_concerts(tm_body()) == []


async def test_find_concerts_queries_music_in_the_city_and_identifies_the_app() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=tm_body(tm_record()))

    async with make_client("test-key", httpx.MockTransport(handler)) as client:
        concerts = await find_concerts(client, "Chicago")

    assert len(concerts) == 1
    request = requests[0]
    assert request.url.path == "/discovery/v2/events.json"
    assert dict(request.url.params) == {
        "apikey": "test-key",
        "city": "Chicago",
        "segmentName": "Music",
        "size": str(ticketmaster.PAGE_SIZE),
        "sort": "date,asc",
    }
    assert request.headers["user-agent"] == ticketmaster.USER_AGENT
    assert "@" not in request.headers["user-agent"]


async def test_find_concerts_retries_a_temporary_failure() -> None:
    responses = iter([httpx.Response(503), httpx.Response(200, json=tm_body(tm_record()))])

    def handler(_: httpx.Request) -> httpx.Response:
        return next(responses)

    async with make_client("test-key", httpx.MockTransport(handler)) as client:
        concerts = await find_concerts(client, "Chicago")

    assert len(concerts) == 1


async def test_find_concerts_reports_failures_without_the_api_key() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"fault": {"faultstring": "Invalid ApiKey"}})

    async with make_client("test-key", httpx.MockTransport(handler)) as client:
        with pytest.raises(TicketmasterError) as caught:
            await find_concerts(client, "Chicago")

    assert "test-key" not in str(caught.value)
    assert caught.value.__cause__ is None


async def test_find_concerts_reports_an_unreadable_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    async with make_client("test-key", httpx.MockTransport(handler)) as client:
        with pytest.raises(TicketmasterError):
            await find_concerts(client, "Chicago")
