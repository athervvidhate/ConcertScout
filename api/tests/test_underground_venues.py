"""Contract tests for underground venue JSON-LD calendars, curated Eventbrite feeds and sync."""

import copy
import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from pydantic import SecretStr

from concert_scout import pool, underground
from concert_scout.app import create_app
from concert_scout.models import Artist, Concert, Place
from concert_scout.sources import eventbrite, jsonld_venues, musicbrainz, ticketmaster
from concert_scout.underground_registry import VENUES, UndergroundVenue, by_slug
from tests.contracts import contract_model, forbidden_http, idle_musicbrainz, settings_with

FIXTURES = Path(__file__).parent / "fixtures"
NOW = dt.datetime(2026, 11, 8, 5, 44, tzinfo=dt.UTC)
NYC = Place(name="New York, New York", lat=40.7128, lon=-74.0060)
LA = Place(name="Los Angeles, California", lat=34.0522, lon=-118.2437)
CHICAGO = Place(name="Chicago, Illinois", lat=41.8781, lon=-87.6298)
NEW_YORK_STATE = Place(name="New York", lat=42.9, lon=-75.5, state_code="NY", country_code="US")
ORGANIZER = "36278734843"


def captured_eventbrite() -> dict[str, Any]:
    return json.loads((FIXTURES / f"eventbrite-{ORGANIZER}.json").read_text())


def venue(slug: str = "nowadays") -> UndergroundVenue:
    found = by_slug(slug)
    assert found is not None
    return found


def test_registry_venues_use_https_valid_zones_and_unique_slugs() -> None:
    assert len(VENUES) >= 8
    slugs = [v.slug for v in VENUES]
    assert len(slugs) == len(set(slugs))
    for room in VENUES:
        assert room.calendar_url.startswith("https://")
        assert by_slug(room.slug) == room


def test_jsonld_extracts_graph_lists_sold_out_relative_urls_and_skips_bad_blocks() -> None:
    room = venue("nowadays")
    html_doc = """
    <html><head>
      <script type="application/ld+json">{ not valid json !!!</script>
      <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@graph": [
            {"@type": "WebSite", "name": "Nowadays"},
            {
              "@type": "MusicEvent",
              "name": "Mister Sunday &amp; Friends",
              "startDate": "2026-11-29T03:00:00Z",
              "eventStatus": "https://schema.org/EventScheduled",
              "url": "/events/mister-sunday",
              "image": {"@type": "ImageObject", "url": "/img/mister.jpg"},
              "performer": [
                {"@type": "Person", "name": "Floating Points"},
                {"@type": "MusicGroup", "name": "Unknown Local Resident"}
              ],
              "offers": [
                {"@type": "Offer", "price": "25", "priceCurrency": "USD", "availability": "https://schema.org/SoldOut"}
              ]
            },
            {
              "@type": "MusicEvent",
              "name": "Cancelled Night",
              "startDate": "2026-11-29T22:00:00-05:00",
              "eventStatus": "https://schema.org/EventCancelled",
              "url": "/events/cancelled"
            },
            {
              "@type": "MusicEvent",
              "name": "Postponed Night",
              "startDate": "2026-11-30T22:00:00-05:00",
              "eventStatus": "https://schema.org/EventPostponed",
              "url": "/events/postponed"
            },
            {
              "@type": "MusicEvent",
              "name": "Past Night",
              "startDate": "2026-11-01T22:00:00-05:00",
              "url": "/events/past"
            },
            {
              "@type": "MusicEvent",
              "name": "Unsafe Link Show",
              "startDate": "2026-12-01T22:00:00-05:00",
              "url": "javascript:alert(1)"
            }
          ]
        }
      </script>
      <script type="application/ld+json; charset=utf-8">
        [
          {
            "@type": ["Event", "MusicEvent"],
            "name": "Date Only Showcase",
            "startDate": "2026-12-05",
            "image": "http://insecure.example/poster.jpg",
            "offers": {"@type": "Offer", "price": 18, "availability": "https://schema.org/InStock"}
          }
        ]
      </script>
    </head><body></body></html>
    """
    events = jsonld_venues.extract_events(html_doc, room, NOW)
    by_name = {e.concert.name: e for e in events}
    assert set(by_name) == {"Mister Sunday & Friends", "Date Only Showcase"}

    mister = by_name["Mister Sunday & Friends"]
    # 2026-11-29T03:00:00Z is 2026-11-28 22:00 in America/New_York (EST, UTC-5).
    assert mister.concert.date == dt.date(2026, 11, 28)
    assert mister.concert.time == dt.time(22, 0)
    assert mister.concert.time_zone == "America/New_York"
    assert mister.concert.source == "venue_calendar"
    assert mister.concert.sold_out is True
    assert mister.concert.url == "https://nowadays.nyc/events/mister-sunday"
    assert mister.concert.image == "https://nowadays.nyc/img/mister.jpg"
    assert mister.concert.price is not None
    assert (mister.concert.price.min, mister.concert.price.max, mister.concert.price.currency) == (
        25.0,
        25.0,
        "USD",
    )
    # Extracted performers stay outside concert.artists until MusicBrainz confirms them.
    assert mister.concert.artists == []
    assert mister.performer_names == ["Floating Points", "Unknown Local Resident"]

    date_only = by_name["Date Only Showcase"]
    assert date_only.concert.date == dt.date(2026, 12, 5)
    assert date_only.concert.time is None
    assert date_only.concert.url == room.calendar_url
    # Insecure image omitted; price omitted because currency was not reported (never invented).
    assert date_only.concert.image is None
    assert date_only.concert.price is None
    assert date_only.concert.sold_out is False


@pytest.mark.parametrize("status", [429, 503])
async def test_jsonld_client_is_polite_and_never_retries(status: int) -> None:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, text="internal upstream stack trace")

    async with jsonld_venues.make_client(httpx.MockTransport(respond)) as client:
        with pytest.raises(jsonld_venues.JsonLdError, match=f"^HTTP {status}$"):
            await jsonld_venues.fetch_calendar(client, venue("nowadays"), NOW)
    assert len(seen) == 1
    assert "ConcertScout" in seen[0].headers["user-agent"]
    assert "@" not in seen[0].headers["user-agent"]


async def test_venue_harvest_confirms_performers_via_musicbrainz_and_prunes_removed() -> None:
    room = venue("nowadays")
    first_html = """
    <script type="application/ld+json">
      [
        {
          "@type": "MusicEvent",
          "name": "Friday Club Night",
          "startDate": "2026-11-20T22:00:00-05:00",
          "url": "/events/friday",
          "performer": [{"name": "Floating Points"}, {"name": "Unconfirmed DJ"}]
        },
        {
          "@type": "MusicEvent",
          "name": "Saturday Night",
          "startDate": "2026-11-21T22:00:00-05:00",
          "url": "/events/saturday",
          "performer": [{"name": "Unconfirmed DJ"}]
        }
      ]
    </script>
    """
    second_html = """
    <script type="application/ld+json">
      {
        "@type": "MusicEvent",
        "name": "Friday Club Night",
        "startDate": "2026-11-20T22:00:00-05:00",
        "url": "/events/friday",
        "performer": [{"name": "Floating Points"}]
      }
    </script>
    """

    def mb_respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "count": 1,
                "artists": [{"name": "Floating Points", "id": "mbid-fp", "score": 100}],
            },
        )

    redis = FakeAsyncRedis()
    pages = [first_html, second_html]

    def venue_respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=pages.pop(0))

    async with (
        jsonld_venues.make_client(httpx.MockTransport(venue_respond)) as venue_client,
        musicbrainz.make_client(httpx.MockTransport(mb_respond)) as mb_client,
    ):
        step1 = await underground.harvest_venue_calendars(
            venue_client, mb_client, redis, NOW, venues=(room,), delay_seconds=0
        )
        found1 = await underground.concerts_near(redis, NYC, None, None, NOW)
        step2 = await underground.harvest_venue_calendars(
            venue_client, mb_client, redis, NOW, venues=(room,), delay_seconds=0
        )
        found2 = await underground.concerts_near(redis, NYC, None, None, NOW)

    assert step1.stored == 2 and step1.confirmed == 1 and step1.error is None
    by_name = {c.name: c for c in found1}
    assert [(a.name, a.mbid) for a in by_name["Friday Club Night"].artists] == [
        ("Floating Points", "mbid-fp")
    ]
    # Unconfirmed performer stays out of artists, never invented.
    assert by_name["Saturday Night"].artists == []

    # Second harvest removes the show that disappeared from the venue calendar.
    assert step2.stored == 1 and step2.removed == 1
    assert [c.name for c in found2] == ["Friday Club Night"]


async def test_eventbrite_harvest_preserves_adr_0002_and_sold_out_without_logging_tokens(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    body = captured_eventbrite()

    redis = FakeAsyncRedis()
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    async with eventbrite.make_client("secret-eb-token", transport) as eb_client:
        step = await underground.harvest_eventbrite_organizers(
            eb_client, redis, [ORGANIZER], NOW, delay_seconds=0
        )

    assert "secret-eb-token" not in caplog.text
    assert step.stored == 2 and step.error is None

    dc = Place(name="Washington, DC", lat=38.9072, lon=-77.0369)
    la_found = await underground.concerts_near(redis, LA, None, None, NOW)
    dc_found = await underground.concerts_near(redis, dc, None, None, NOW)
    assert len(la_found) == 1 and len(dc_found) == 1
    for concert in [*la_found, *dc_found]:
        assert concert.source == "eventbrite"
        # ADR 0002: Eventbrite titles (including unofficial afterparties) never become Artists.
        assert concert.artists == []
    assert "Unofficial Afterparty" in la_found[0].name and la_found[0].sold_out is True
    assert "Unofficial Afterparty" in dc_found[0].name and dc_found[0].sold_out is False
    assert underground.holds(la_found[0].id)
    assert await underground.find(redis, la_found[0].id) == la_found[0]


async def test_pool_reads_local_underground_store_without_live_scraping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    room = venue("nowadays")
    redis = FakeAsyncRedis()
    venue_concert = Concert(
        id="venue:nowadays:abc123",
        name="Floating Points All Night",
        url="https://nowadays.nyc/events/fp",
        source="venue_calendar",
        artists=[Artist(name="Floating Points", mbid="mbid-fp")],
        date=dt.date(2026, 11, 20),
        time=dt.time(22, 0),
        time_zone="America/New_York",
        venue=room.name,
        city=room.city,
        region=room.region,
    )
    eb_concert = Concert(
        id="eventbrite:999001",
        name="Late Night Disco Warehouse",
        url="https://www.eventbrite.com/e/999001",
        source="eventbrite",
        sold_out=True,
        artists=[],
        date=dt.date(2026, 11, 20),
        time=dt.time(23, 0),
        time_zone="America/New_York",
        venue="Public Records",
        city="Brooklyn",
        region="NY",
    )
    await underground.store_source(
        redis,
        "venue:nowadays",
        [
            underground.StoredListing(
                concert=venue_concert,
                latitude=room.lat,
                longitude=room.lon,
                source_key="venue:nowadays",
            )
        ],
    )
    await underground.store_source(
        redis,
        "eventbrite:123",
        [
            underground.StoredListing(
                concert=eb_concert,
                latitude=40.6808,
                longitude=-73.9873,
                source_key="eventbrite:123",
            )
        ],
    )

    monkeypatch.setattr(ticketmaster, "find_concerts", AsyncMock(return_value=[]))
    async with ticketmaster.make_client("unused", httpx.MockTransport(forbidden_http)) as client:
        found = await pool.find_concerts(
            client,
            idle_musicbrainz(),
            redis,
            NYC,
            [],
            dt.date(2026, 11, 20),
            dt.date(2026, 11, 20),
            NOW,
        )
        # Saved Concert lookup resolves underground IDs locally without calling Ticketmaster.
        assert await pool.find_concert(client, redis, venue_concert.id) == venue_concert
        assert await pool.find_concert(client, redis, eb_concert.id) == eb_concert
        with pytest.raises(pool.ConcertNotFound):
            await pool.find_concert(client, redis, "venue:nowadays:missing")

    assert {c.id for c in found} == {venue_concert.id, eb_concert.id}
    # Eventbrite listing must stay non-Lineup even after flowing through pool.find_concerts.
    eb_out = next(c for c in found if c.id == eb_concert.id)
    assert eb_out.artists == [] and eb_out.sold_out is True

    # Geospatial, state, country, and date filters isolate results accurately.
    assert await underground.concerts_near(redis, CHICAGO, None, None, NOW) == []
    statewide = await underground.concerts_near(redis, NEW_YORK_STATE, None, None, NOW)
    assert {c.id for c in statewide} == {venue_concert.id, eb_concert.id}
    london = Place(name="London", lat=51.5, lon=-0.1, country_code="GB")
    assert await underground.concerts_near(redis, london, None, None, NOW) == []
    assert (
        await underground.concerts_near(
            redis, NYC, dt.date(2026, 11, 25), dt.date(2026, 11, 30), NOW
        )
        == []
    )


def test_conservative_deduplication_against_ticketmaster_and_jambase() -> None:
    day = dt.date(2026, 11, 20)
    tm_show = Concert(
        id="tm:1",
        name="Floating Points",
        url="https://tickets.example/tm1",
        source="ticketmaster",
        artists=[Artist(name="Floating Points", mbid="mbid-fp")],
        date=day,
        time=dt.time(22, 0),
        venue="Nowadays",
        city="Queens",
        region="NY",
    )
    vc_duplicate = tm_show.model_copy(
        update={
            "id": "venue:nowadays:dup",
            "source": "venue_calendar",
            "time": dt.time(22, 30),
            "image": "https://nowadays.nyc/fp.jpg",
        }
    )
    vc_late_set = vc_duplicate.model_copy(
        update={"id": "venue:nowadays:late", "time": dt.time(1, 0), "image": None}
    )
    jb_show = Concert(
        id="jambase:55",
        name="Mister Sunday",
        url="https://jambase.example/55",
        source="jambase",
        artists=[Artist(name="Justin Carter")],
        date=day,
        time=dt.time(15, 0),
        venue="Nowadays",
        city="Queens",
        region="NY",
    )
    eb_duplicate = Concert(
        id="eventbrite:dup",
        name="Mister Sunday at Nowadays",
        url="https://eventbrite.example/dup",
        source="eventbrite",
        artists=[],
        date=day,
        time=dt.time(15, 0),
        venue="Nowadays",
        city="Queens",
        region="NY",
    )
    eb_afterparty = Concert(
        id="eventbrite:after",
        name="Floating Points Unofficial Afterparty",
        url="https://eventbrite.example/after",
        source="eventbrite",
        artists=[],
        date=day,
        time=dt.time(22, 30),
        venue="Nowadays",
        city="Queens",
        region="NY",
    )
    eb_unrelated = Concert(
        id="eventbrite:other",
        name="Deep House Listening Session",
        url="https://eventbrite.example/other",
        source="eventbrite",
        artists=[],
        date=day,
        time=dt.time(22, 0),
        venue="Nowadays",
        city="Queens",
        region="NY",
    )

    merged = pool.merge_sources(
        [tm_show],
        [jb_show, vc_duplicate, vc_late_set, eb_duplicate, eb_afterparty, eb_unrelated],
    )
    ids = [c.id for c in merged]
    # Primary Ticketmaster show deduplicates venue_calendar duplicate and borrows its missing photo.
    assert "tm:1" in ids
    assert merged[0].image == "https://nowadays.nyc/fp.jpg"
    assert "venue:nowadays:dup" not in ids
    # Distinct late set stays.
    assert "venue:nowadays:late" in ids
    # Same-venue, same-time, matching-title Eventbrite listing deduplicates against JamBase.
    assert "jambase:55" in ids
    assert "eventbrite:dup" not in ids
    # Unrelated non-Lineup show and unofficial afterparty are never falsely deduplicated.
    assert "eventbrite:after" in ids
    assert "eventbrite:other" in ids


async def test_sync_underground_route_auth_locking_and_safe_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(underground, "DEFAULT_DELAY_SECONDS", 0)
    monkeypatch.setattr(underground, "VENUES", (venue("nowadays"),))

    # Unset cron_secret means the route does not exist.
    no_cron_app = create_app(
        settings_with(), httpx.MockTransport(forbidden_http), FakeAsyncRedis(), contract_model()
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(no_cron_app), base_url="http://test"
    ) as client:
        assert (await client.post("/sync-underground")).status_code == 404

    calendar_html = """
    <script type="application/ld+json">
      {
        "@type": "MusicEvent",
        "name": "Club Showcase",
        "startDate": "2027-06-12T22:00:00-04:00",
        "url": "/events/showcase",
        "performer": [{"name": "Floating Points"}]
      }
    </script>
    """
    eb_body = copy.deepcopy(captured_eventbrite())
    # Move Eventbrite fixture dates far ahead so they stay upcoming against wall-clock UTC now.
    for ev in eb_body["events"]:
        ev["start"]["local"] = "2027-06-14T22:00:00"
        ev["end"]["utc"] = "2027-06-15T06:00:00Z"

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "nowadays.nyc":
            return httpx.Response(200, text=calendar_html)
        if request.url.host == "musicbrainz.org":
            return httpx.Response(
                200,
                json={
                    "count": 1,
                    "artists": [{"name": "Floating Points", "id": "mbid-fp", "score": 100}],
                },
            )
        if request.url.host == "www.eventbriteapi.com":
            return httpx.Response(200, json=eb_body)
        return forbidden_http(request)

    redis = FakeAsyncRedis()
    app = create_app(
        settings_with(
            cron_secret=SecretStr("top-cron-secret"),
            eventbrite_token=SecretStr("secret-eb-token"),
            eventbrite_organizer_ids=f" {ORGANIZER} , {ORGANIZER} ",
        ),
        httpx.MockTransport(respond),
        redis,
        contract_model(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        assert (await client.post("/sync-underground")).status_code == 401
        wrong = await client.post(
            "/sync-underground", headers={"Authorization": "Bearer wrong-secret"}
        )
        assert wrong.status_code == 401 and wrong.json()["code"] == "not_scheduler"

        # Lock prevents concurrent harvest.
        await redis.set(underground.LOCK, "held-by-other", ex=120)
        locked = await client.post(
            "/sync-underground", headers={"Authorization": "Bearer top-cron-secret"}
        )
        assert locked.status_code == 200
        assert locked.json() == [
            {
                "name": "underground",
                "requests": 0,
                "stored": 0,
                "removed": 0,
                "confirmed": 0,
                "seconds": 0.0,
                "error": "sync already running",
            }
        ]
        await redis.delete(underground.LOCK)

        # Authenticated run harvests both sources and releases the lock.
        ran = await client.post(
            "/sync-underground", headers={"Authorization": "Bearer top-cron-secret"}
        )
        assert ran.status_code == 200
        assert "secret-eb-token" not in ran.text
        steps = {step["name"]: step for step in ran.json()}
        assert steps["venue_calendars"]["stored"] == 1
        assert steps["venue_calendars"]["confirmed"] == 1
        assert steps["eventbrite_organizers"]["stored"] == 2
        assert "prune" in steps
        assert not await redis.exists(underground.LOCK)
