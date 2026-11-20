"""Venue room character (MusicBrainz Places + Wikidata) and Followed Venues contracts."""

import json
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from pydantic import SecretStr

from concert_scout import alerts, pool
from concert_scout.app import create_app, make_services
from concert_scout.models import Concert
from concert_scout.sources import musicbrainz, resend, supabase, venues
from concert_scout.sources.supabase import FollowedArtist, FollowedVenue
from tests import supabase_stack
from tests.contracts import (
    CONCERTS,
    NOW,
    PLACE,
    contract_model,
    forbidden_http,
    install_sources,
    settings_with,
)
from tests.test_alerts import ALICE, Stack
from tests.test_alerts import run as run_alerts


@pytest.mark.parametrize(
    ("capacity", "tier"),
    [
        (None, None),
        (0, None),
        (-50, None),
        (1, "Intimate club"),
        (500, "Intimate club"),
        (501, "Club / Ballroom"),
        (575, "Club / Ballroom"),
        (1500, "Club / Ballroom"),
        (1501, "Theater"),
        (5000, "Theater"),
        (5001, "Amphitheater / Large hall"),
        (15000, "Amphitheater / Large hall"),
        (15001, "Arena / Stadium"),
        (20000, "Arena / Stadium"),
    ],
)
def test_capacity_maps_strictly_into_factual_tiers(
    capacity: int | None, tier: venues.VenueTier | None
) -> None:
    assert venues.capacity_tier(capacity) == tier


@pytest.mark.parametrize(
    ("name", "city", "expected"),
    [
        ("The Bowery Ballroom", "New York", "bowery ballroom::new york"),
        ("Bowery  Ballroom", "new york", "bowery ballroom::new york"),
        ("Red Rocks Amphitheatre", None, "red rocks amphitheatre"),
        ("Red Rocks Amphitheatre", "   ", "red rocks amphitheatre"),
        ("Café du Nord", "San Francisco", "cafe du nord::san francisco"),
        ("9:30 Club", "Washington", "930 club::washington"),
    ],
)
def test_venue_key_normalizes_name_and_city(name: str, city: str | None, expected: str) -> None:
    assert venues.venue_key(name, city) == expected


def test_distance_km_distinguishes_within_and_beyond_one_kilometer() -> None:
    # Bowery Ballroom (40.7204, -73.9934) vs ~110m north vs ~2.2km north.
    assert venues.distance_km(40.7204, -73.9934, 40.7214, -73.9934) < 0.2
    assert venues.distance_km(40.7204, -73.9934, 40.7404, -73.9934) > 2.0


def _wikidata_entity(
    qid: str,
    label: str,
    *,
    capacity: int | None = None,
    p31: list[str] | None = None,
    coords: tuple[float, float] | None = None,
) -> dict[str, Any]:
    claims: dict[str, Any] = {}
    if capacity is not None:
        claims["P1083"] = [
            {
                "rank": "normal",
                "mainsnak": {"datavalue": {"value": {"amount": f"+{capacity}"}}},
            }
        ]
    if p31:
        claims["P31"] = [
            {"rank": "normal", "mainsnak": {"datavalue": {"value": {"id": item}}}} for item in p31
        ]
    if coords is not None:
        claims["P625"] = [
            {
                "rank": "normal",
                "mainsnak": {
                    "datavalue": {"value": {"latitude": coords[0], "longitude": coords[1]}}
                },
            }
        ]
    return {"id": qid, "labels": {"en": {"value": label}}, "claims": claims}


async def test_verified_venue_within_one_km_returns_facts_and_caches_60_days() -> None:
    calls: list[str] = []
    mbid = "11111111-1111-1111-1111-111111111111"
    qid = "Q4950892"

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.url.host}{request.url.path}")
        if request.url.host == "musicbrainz.org" and request.url.path == "/ws/2/place":
            return httpx.Response(
                200,
                json={
                    "places": [
                        {
                            "id": mbid,
                            "score": 100,
                            "name": "Bowery Ballroom",
                            "type": "Venue",
                            "area": {"name": "New York"},
                            "coordinates": {"latitude": "40.7204", "longitude": "-73.9934"},
                        }
                    ]
                },
            )
        if request.url.host == "musicbrainz.org" and request.url.path == f"/ws/2/place/{mbid}":
            return httpx.Response(
                200,
                json={
                    "id": mbid,
                    "relations": [
                        {"url": {"resource": f"https://www.wikidata.org/wiki/{qid}"}},
                    ],
                },
            )
        if request.url.host == "www.wikidata.org" and request.url.path == "/w/api.php":
            return httpx.Response(
                200,
                json={
                    "entities": {
                        qid: _wikidata_entity(
                            qid,
                            "Bowery Ballroom",
                            capacity=575,
                            p31=["Q8719053"],
                            coords=(40.72042, -73.99338),
                        )
                    }
                },
            )
        raise AssertionError(f"Unexpected HTTP: {request.url}")

    redis = FakeAsyncRedis()
    transport = httpx.MockTransport(handle)
    async with (
        musicbrainz.make_client(transport) as mb_client,
        venues.make_wikidata_client(transport) as wd_client,
    ):
        found = await venues.lookup(
            mb_client, wd_client, redis, "Bowery Ballroom", "New York", 40.7205, -73.9935
        )
        cached = await venues.lookup(
            mb_client, wd_client, redis, "Bowery Ballroom", "New York", 40.7205, -73.9935
        )

    assert found == venues.VenueCharacter(
        name="Bowery Ballroom",
        city="New York",
        capacity=575,
        tier="Club / Ballroom",
        venue_type="Music venue",
        mbid=mbid,
        wikidata_id=qid,
    )
    assert cached == found
    assert len(calls) == 3
    key = venues.cache_key("Bowery Ballroom", "New York", 40.7205, -73.9935)
    ttl = await redis.ttl(key)
    assert 59 * 86400 < ttl <= 60 * 86400
    assert (
        await venues.cached_character(redis, "Bowery Ballroom", "New York", 40.7205, -73.9935)
        == found
    )


async def test_namesake_beyond_one_km_is_rejected_and_omits_facts() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.host == "musicbrainz.org" and request.url.path == "/ws/2/place":
            return httpx.Response(
                200,
                json={
                    "places": [
                        {
                            "id": "22222222-2222-2222-2222-222222222222",
                            "score": 100,
                            "name": "The Fillmore",
                            "type": "Venue",
                            "area": {"name": "San Francisco"},
                            # SF coordinates, far from Detroit (42.337, -83.052).
                            "coordinates": {"latitude": "37.7842", "longitude": "-122.4331"},
                        }
                    ]
                },
            )
        if request.url.host == "www.wikidata.org":
            query = parse_qs(request.url.query.decode())
            if query.get("action") == ["wbsearchentities"]:
                return httpx.Response(200, json={"search": [{"id": "Q1320987"}]})
            return httpx.Response(
                200,
                json={
                    "entities": {
                        "Q1320987": _wikidata_entity(
                            "Q1320987",
                            "The Fillmore",
                            capacity=1315,
                            p31=["Q8719053"],
                            coords=(37.7842, -122.4331),
                        )
                    }
                },
            )
        raise AssertionError(f"Unexpected HTTP: {request.url}")

    redis = FakeAsyncRedis()
    transport = httpx.MockTransport(handle)
    async with (
        musicbrainz.make_client(transport) as mb_client,
        venues.make_wikidata_client(transport) as wd_client,
    ):
        found = await venues.lookup(
            mb_client, wd_client, redis, "The Fillmore", "Detroit", 42.337, -83.052
        )

    assert found == venues.VenueCharacter(name="The Fillmore", city="Detroit")
    assert found.capacity is None and found.tier is None and found.venue_type is None


async def test_wikidata_coord_fallback_verifies_within_one_km() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.host == "musicbrainz.org":
            return httpx.Response(200, json={"places": []})
        if request.url.host == "www.wikidata.org":
            query = parse_qs(request.url.query.decode())
            if query.get("action") == ["wbsearchentities"]:
                return httpx.Response(200, json={"search": [{"id": "Q999"}]})
            return httpx.Response(
                200,
                json={
                    "entities": {
                        "Q999": _wikidata_entity(
                            "Q999",
                            "Smartbar",
                            capacity=400,
                            p31=["Q622425"],
                            coords=(41.9498, -87.6589),
                        )
                    }
                },
            )
        raise AssertionError(f"Unexpected HTTP: {request.url}")

    redis = FakeAsyncRedis()
    transport = httpx.MockTransport(handle)
    async with (
        musicbrainz.make_client(transport) as mb_client,
        venues.make_wikidata_client(transport) as wd_client,
    ):
        found = await venues.lookup(
            mb_client, wd_client, redis, "Smartbar", "Chicago", 41.9499, -87.6588
        )

    assert found.capacity == 400
    assert found.tier == "Intimate club"
    assert found.venue_type == "Nightclub"
    assert found.wikidata_id == "Q999"


async def test_upstream_failure_omits_facts_without_caching_failure() -> None:
    def fail(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    redis = FakeAsyncRedis()
    transport = httpx.MockTransport(fail)
    async with (
        musicbrainz.make_client(transport) as mb_client,
        venues.make_wikidata_client(transport) as wd_client,
    ):
        found = await venues.lookup(
            mb_client, wd_client, redis, "Elsewhere", "Brooklyn", 40.7094, -73.9232
        )

    assert found == venues.VenueCharacter(name="Elsewhere", city="Brooklyn")
    assert await venues.cached_character(redis, "Elsewhere", "Brooklyn", 40.7094, -73.9232) is None


async def test_venue_route_validates_params_and_rate_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_sources(monkeypatch)
    monkeypatch.setattr(venues, "VENUE_PER_HOUR", 2)
    app = create_app(
        settings_with(),
        httpx.MockTransport(forbidden_http),
        FakeAsyncRedis(),
        contract_model(),
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as api:
        missing = await api.get("/venue")
        assert missing.status_code == 422
        assert missing.json()["code"] == "invalid_venue"

        half_coords = await api.get("/venue", params={"name": "Source Hall", "lat": 37.77})
        assert half_coords.status_code == 422
        assert half_coords.json()["code"] == "invalid_venue"

        verified = await api.get("/venue", params={"name": "Source Hall", "city": "San Francisco"})
        assert verified.status_code == 200
        assert verified.json() == {
            "name": "Source Hall",
            "city": "San Francisco",
            "capacity": 450,
            "tier": "Intimate club",
            "venue_type": "Music venue",
        }

        unverified = await api.get(
            "/venue", params={"name": "Second Hall", "city": "San Francisco"}
        )
        assert unverified.status_code == 200
        assert unverified.json() == {"name": "Second Hall", "city": "San Francisco"}

        limited = await api.get("/venue", params={"name": "Source Hall", "city": "San Francisco"})
        assert limited.status_code == 429
        assert limited.json()["code"] == "visitor_limit"


def test_matching_folds_followed_venues_and_deduplicates_with_artists() -> None:
    followed_artists = [FollowedArtist(artist_key="contract artist", name="Contract Artist")]
    followed_venues = [
        # Matches contract-one (already matched by artist) and contract-two (new via venue).
        FollowedVenue(
            venue_key=venues.venue_key("Source Hall", "San Francisco"),
            name="Source Hall",
            city="San Francisco",
        ),
        FollowedVenue(
            venue_key=venues.venue_key("Second Hall", "San Francisco"),
            name="Second Hall",
            city="San Francisco",
        ),
        # Namesake in another city must not match Oakland's Third Hall.
        FollowedVenue(
            venue_key=venues.venue_key("Third Hall", "Chicago"),
            name="Third Hall",
            city="Chicago",
        ),
    ]
    found = alerts.matching(CONCERTS, followed_artists, followed_venues)
    assert [c.id for c in found] == ["contract-one", "contract-two", "contract-three"]


async def test_daily_alert_folds_followed_venues_into_one_deduplicated_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    no_lineup = CONCERTS[1].model_copy(
        update={"id": "venue-only-show", "name": "Late Night Showcase", "artists": []}
    )

    async def find_concerts(*_: Any, **__: Any) -> list[Concert]:
        return [*CONCERTS, no_lineup]

    monkeypatch.setattr(pool, "find_concerts", find_concerts)
    stack = Stack()
    stack.person(ALICE, "alice@example.com")
    stack.alerts_on(ALICE, PLACE, "Contract Artist")
    stack.followed_venues.append(
        {
            "user_id": ALICE,
            "venue_key": venues.venue_key("Second Hall", "San Francisco"),
            "name": "Second Hall",
            "city": "San Francisco",
            "lat": None,
            "lon": None,
        }
    )

    first = await run_alerts(stack)
    second = await run_alerts(stack)

    assert first.sent == 1
    assert second.sent == 0
    assert len(stack.emails) == 1
    [(email, _)] = stack.emails
    assert email["subject"] == "4 new Concerts from Artists and venues you follow"
    assert "Second Contract Artist" in email["text"]
    assert "Late Night Showcase" in email["text"]
    assert sorted(r["concert_id"] for r in stack.sent) == [
        "contract-one",
        "contract-three",
        "contract-two",
        "venue-only-show",
    ]


@pytest.mark.supabase
async def test_followed_venues_rls_and_cascade_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    install_sources(monkeypatch)
    app = create_app(
        settings_with(
            supabase_url=supabase_stack.URL,
            supabase_publishable_key=supabase_stack.PUBLISHABLE_KEY,
            supabase_secret_key=SecretStr(supabase_stack.secret_key()),
        ),
        supabase_stack.stack_transport(httpx.MockTransport(forbidden_http)),
        FakeAsyncRedis(),
        contract_model(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://127.0.0.1:8000"
    ) as api:
        owner = supabase_stack.new_person()
        other = supabase_stack.new_person()
        owner_headers = {
            "Authorization": f"Bearer {owner.token}",
            "Origin": "http://localhost:3000",
        }
        other_headers = {
            "Authorization": f"Bearer {other.token}",
            "Origin": "http://localhost:3000",
        }

        for payload in (
            {"name": "The Bowery Ballroom", "city": "New York", "lat": 40.7204, "lon": -73.9934},
            {"name": "Bowery  Ballroom", "city": "new york"},
            {"name": "Source Hall", "city": "San Francisco"},
        ):
            res = await api.post("/account/followed-venues", json=payload, headers=owner_headers)
            assert res.status_code == 200

        view = (await api.get("/account/alerts", headers=owner_headers)).json()
        assert [v["venue_key"] for v in view["followed_venues"]] == [
            "bowery ballroom::new york",
            "source hall::san francisco",
        ]
        # Duplicate follow kept the first spelling and coordinates.
        assert view["followed_venues"][0]["name"] == "The Bowery Ballroom"
        assert view["followed_venues"][0]["lat"] == pytest.approx(40.7204)

        # Other account cannot see or delete owner's followed venues, nor write via PostgREST.
        assert (await api.get("/account/alerts", headers=other_headers)).json()[
            "followed_venues"
        ] == []
        await api.delete(
            "/account/followed-venues/bowery ballroom::new york", headers=other_headers
        )
        assert (
            len((await api.get("/account/alerts", headers=owner_headers)).json()["followed_venues"])
            == 2
        )
        with supabase_stack.rest(other.token) as rest:
            forged = {
                "user_id": owner.id,
                "venue_key": "forged::city",
                "name": "Forged",
            }
            assert rest.post("/followed_venues", json=forged).status_code in (401, 403)
            assert rest.get("/followed_venues", params={"select": "name"}).json() == []

        # Owner can unfollow one venue.
        gone = await api.delete(
            "/account/followed-venues/bowery ballroom::new york", headers=owner_headers
        )
        assert gone.status_code == 204
        assert [
            v["venue_key"]
            for v in (await api.get("/account/alerts", headers=owner_headers)).json()[
                "followed_venues"
            ]
        ] == ["source hall::san francisco"]

        # Deleting the Account cascades cleanly to followed_venues.
        assert (await api.delete("/account", headers=owner_headers)).status_code == 204
        async with supabase.make_client(supabase_stack.URL) as client:
            remaining = await supabase.followed_venues_by(
                client, SecretStr(supabase_stack.secret_key()), [owner.id]
            )
        assert remaining == {}


@pytest.mark.supabase
async def test_real_alert_run_includes_followed_venues(monkeypatch: pytest.MonkeyPatch) -> None:
    install_sources(monkeypatch)
    person = supabase_stack.new_person()
    secret = SecretStr(supabase_stack.secret_key())
    emails: list[dict[str, object]] = []

    def mail(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.resend.com"
        emails.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "email"})

    transport = supabase_stack.stack_transport(httpx.MockTransport(mail))
    services = make_services(settings_with(), transport, FakeAsyncRedis(), contract_model())
    async with (
        supabase.make_client(supabase_stack.URL, transport) as client,
        resend.make_client("re_test", transport) as mail_client,
    ):
        account = supabase.Account(person.id, person.token, 0)
        await supabase.follow_venue(
            client,
            secret,
            account,
            FollowedVenue(
                venue_key=venues.venue_key("Second Hall", "San Francisco"),
                name="Second Hall",
                city="San Francisco",
            ),
        )
        await supabase.set_alert_place(client, secret, person.id, PLACE)
        await supabase.set_alerts_enabled(client, secret, person.id, True)

        await alerts.run(
            services, client, secret, mail_client, "https://site.test", "https://api.test", NOW
        )
        await alerts.run(
            services, client, secret, mail_client, "https://site.test", "https://api.test", NOW
        )

        mine = [e for e in emails if e["to"] == [person.email]]
        assert len(mine) == 1
        sent = await supabase.sent_to(client, secret, [person.id])
        assert sent[person.id] == {CONCERTS[1].id}
        await supabase.delete_user(client, secret, account)
        assert await supabase.followed_venues_by(client, secret, [person.id]) == {}
