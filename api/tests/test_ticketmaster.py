import datetime as dt
from typing import Any

import httpx
import pytest
from fakeredis import FakeAsyncRedis

from concert_scout.models import Price
from concert_scout.sources import ticketmaster
from concert_scout.sources.http import USER_AGENT
from concert_scout.sources.ticketmaster import (
    TicketmasterError,
    find_artist_concerts,
    find_concerts,
    make_client,
    normalize,
    parse_concert,
    parse_concerts,
    rounded_point,
)
from tests.conftest import CHICAGO, tm_body, tm_record

POINT = rounded_point(CHICAGO)
START = dt.date(2026, 11, 1)
END = dt.date(2026, 11, 30)


async def search(handler: Any, start: dt.date = START, end: dt.date = END) -> list[Any]:
    async with make_client("test-key", httpx.MockTransport(handler)) as client:
        return await find_concerts(client, FakeAsyncRedis(), POINT, start, end)


def window_of(request: httpx.Request) -> tuple[dt.date, dt.date]:
    first, last = request.url.params["localStartDateTime"].split(",")
    return dt.date.fromisoformat(first[:10]), dt.date.fromisoformat(last[:10])


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


async def test_find_concerts_queries_music_around_the_point_and_identifies_the_app() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=tm_body(tm_record()))

    concerts = await search(handler)

    assert len(concerts) == 1
    assert len(requests) == 1
    request = requests[0]
    assert request.url.path == "/discovery/v2/events.json"
    assert dict(request.url.params) == {
        "apikey": "test-key",
        "geoPoint": "dp3wn",
        "radius": "50",
        "unit": "miles",
        "segmentName": "Music",
        "size": str(ticketmaster.PAGE_SIZE),
        "sort": "date,name,asc",
        "page": "0",
        # The venue's local dates, so a late Concert never shifts a day.
        "localStartDateTime": "2026-11-01T00:00:00,2026-11-30T23:59:59",
    }
    assert request.headers["user-agent"] == USER_AGENT
    assert "@" not in request.headers["user-agent"]


async def test_find_concerts_walks_every_page() -> None:
    pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        pages.append(page)
        return httpx.Response(200, json=tm_body(tm_record(id=f"id-{page}"), total=450))

    concerts = await search(handler)

    assert sorted(pages) == [0, 1, 2]
    assert {concert.id for concert in concerts} == {"id-0", "id-1", "id-2"}


async def test_a_full_last_page_is_not_followed_by_an_empty_one() -> None:
    pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        pages.append(int(request.url.params["page"]))
        return httpx.Response(200, json=tm_body(tm_record(), total=ticketmaster.PAGE_SIZE * 2))

    await search(handler)

    assert sorted(pages) == [0, 1]


async def test_a_window_over_the_cap_splits_until_every_part_fits() -> None:
    windows: list[tuple[dt.date, dt.date]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        first, last = window_of(request)
        windows.append((first, last))
        days = (last - first).days + 1
        return httpx.Response(200, json=tm_body(tm_record(id=str(first)), total=days * 60))

    concerts = await search(handler)

    # 30 days at 60 a day is 1,800, so the 15-day halves hold 900 each and need no further split.
    assert set(windows) == {
        (dt.date(2026, 11, 1), dt.date(2026, 11, 30)),
        (dt.date(2026, 11, 1), dt.date(2026, 11, 15)),
        (dt.date(2026, 11, 16), dt.date(2026, 11, 30)),
    }
    assert len({concert.id for concert in concerts}) == 2


async def test_a_single_day_over_the_cap_keeps_what_ticketmaster_serves() -> None:
    pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        pages.append(int(request.url.params["page"]))
        return httpx.Response(200, json=tm_body(tm_record(), total=1500))

    await search(handler, START, START)

    assert sorted(pages) == [0, 1, 2, 3, 4]


async def test_find_artist_concerts_keeps_only_the_named_artists_lineups() -> None:
    requests: list[httpx.Request] = []
    other = {"_embedded": {"attractions": [{"name": "Khruangbin Tribute Band"}]}}

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=tm_body(tm_record(), tm_record(id="other", **other)))

    async with make_client("test-key", httpx.MockTransport(handler)) as client:
        concerts = await find_artist_concerts(client, FakeAsyncRedis(), "khruangbin", POINT)

    assert [concert.id for concert in concerts] == ["vvG18Z_ueUZbii"]
    assert requests[0].url.params["keyword"] == "khruangbin"
    assert requests[0].url.params["geoPoint"] == POINT
    assert "localStartDateTime" not in requests[0].url.params


async def test_find_artist_concerts_can_look_anywhere() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=tm_body())

    async with make_client("test-key", httpx.MockTransport(handler)) as client:
        await find_artist_concerts(client, FakeAsyncRedis(), "Khruangbin", None)

    assert "geoPoint" not in requests[0].url.params
    assert "radius" not in requests[0].url.params


def test_normalize_ignores_case_accents_and_spacing() -> None:
    assert normalize("  Beyoncé   KNOWLES ") == "beyonce knowles"


async def test_find_concerts_retries_a_temporary_failure() -> None:
    responses = iter([httpx.Response(503), httpx.Response(200, json=tm_body(tm_record()))])

    def handler(_: httpx.Request) -> httpx.Response:
        return next(responses)

    assert len(await search(handler)) == 1


async def test_find_concerts_reports_failures_without_the_api_key() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"fault": {"faultstring": "Invalid ApiKey"}})

    with pytest.raises(TicketmasterError) as caught:
        await search(handler)

    assert "test-key" not in str(caught.value)
    assert caught.value.__cause__ is None


async def test_find_concerts_reports_an_unreadable_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    with pytest.raises(TicketmasterError):
        await search(handler)
