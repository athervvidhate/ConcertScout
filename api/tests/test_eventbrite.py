"""Real selected-field captures; mutations model privacy/status and broken-page failures."""

import copy
import datetime as dt
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from concert_scout.sources import eventbrite

FIXTURES = Path(__file__).parent / "fixtures"
NOW = dt.datetime(2026, 11, 8, 5, 44, tzinfo=dt.UTC)
ORGANIZER = "36278734843"


def captured(organizer: str = ORGANIZER) -> dict[str, Any]:
    return json.loads((FIXTURES / f"eventbrite-{organizer}.json").read_text())


def test_actual_afterparty_is_not_presented_as_an_artist_performance() -> None:
    record = captured()["events"][1]
    listing = eventbrite.parse_listing(record, NOW)
    assert listing is not None
    concert = listing.concert
    assert "Unofficial Afterparty" in concert.name
    assert concert.artists == []
    assert concert.id == f"eventbrite:{record['id']}"
    assert concert.url == record["url"]
    assert concert.venue == "33 Taps DTLA"
    assert concert.city == "Los Angeles" and concert.region == "CA"
    assert concert.date == dt.date(2026, 11, 9) and concert.time == dt.time(22)
    assert concert.time_zone == "America/Los_Angeles"
    assert concert.image == record["logo"]["url"]
    assert concert.price is not None
    assert concert.price.min == float(
        record["ticket_availability"]["minimum_ticket_price"]["major_value"]
    )
    assert concert.general_sale is None and concert.presales == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("listed", False),
        ("shareable", False),
        ("online_event", True),
        ("status", "canceled"),
        ("status", "draft"),
        ("category_id", "105"),
        ("hide_start_date", True),
        ("is_series_parent", True),
    ],
)
def test_ineligible_records_never_become_public_concerts(field: str, value: Any) -> None:
    record = copy.deepcopy(captured()["events"][1])
    record[field] = value
    assert eventbrite.parse_listing(record, NOW) is None


def test_past_events_and_missing_facts_are_not_recreated() -> None:
    record = captured()["events"][1]
    assert eventbrite.parse_listing(record, NOW + dt.timedelta(days=30)) is None
    record.pop("ticket_availability")
    record.pop("logo")
    listing = eventbrite.parse_listing(record, NOW)
    assert listing is not None
    assert listing.concert.price is None and listing.concert.image is None


async def test_complete_organizer_capture_uses_no_account_or_search_endpoint() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=captured())

    async with eventbrite.make_client("unused", httpx.MockTransport(respond)) as client:
        listings = await eventbrite.organizer_listings(client, ORGANIZER, NOW)
    assert len(listings) == 2  # One listing has started; another is Arts, not Music.
    assert len(requests) == 1
    assert requests[0].url.path == f"/v3/organizers/{ORGANIZER}/events/"
    assert requests[0].headers["authorization"] == "Bearer unused"
    assert requests[0].url.params["status"] == "live"
    assert all(not row.concert.artists for row in listings)


async def test_truncated_or_foreign_response_never_returns_partial_data() -> None:
    for kind in ["truncated", "foreign", "too-many-pages"]:
        body = captured()
        if kind == "truncated":
            body["events"].pop()
        elif kind == "foreign":
            body["events"][0]["organizer_id"] = "other-organizer"
        else:
            body["pagination"]["has_more_items"] = True
        async with eventbrite.make_client(
            "unused", httpx.MockTransport(lambda _, body=body: httpx.Response(200, json=body))
        ) as client:
            with pytest.raises(eventbrite.EventbriteError):
                await eventbrite.organizer_listings(client, ORGANIZER, NOW)


@pytest.mark.parametrize("status", [401, 403, 429, 503])
async def test_upstream_errors_are_safe_and_never_retried(status: int) -> None:
    calls = 0

    def respond(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status, text="private response body")

    async with eventbrite.make_client("private-key", httpx.MockTransport(respond)) as client:
        with pytest.raises(eventbrite.EventbriteError, match=f"^HTTP {status}$"):
            await eventbrite.organizer_listings(client, ORGANIZER, NOW)
    assert calls == 1
