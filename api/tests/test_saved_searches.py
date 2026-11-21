"""Saved Searches: CRUD, 5-cap, weekly reruns, spend-cap priority, and RLS (Issue #89)."""

import datetime as dt
import json
import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from fastapi.sse import ServerSentEvent
from pydantic import SecretStr

from concert_scout import alerts, limits, pipeline, pool, saved_searches
from concert_scout.app import create_app, make_services
from concert_scout.models import Artist, Concert, Place, Poster, Reading, Recommendation
from concert_scout.sources import resend, supabase
from tests import supabase_stack as sb_stack
from tests.contracts import (
    CONCERTS,
    NOW,
    PLACE,
    contract_model,
    forbidden_http,
    install_sources,
    settings_with,
)

SECRET = SecretStr("test-secret-key")
SUPABASE = "https://supabase.test"
ALICE = "00000000-0000-0000-0000-00000000000a"
BOB = "00000000-0000-0000-0000-00000000000b"
ORIGIN = "http://localhost:3000"


def _rec(
    concert_id: str,
    *,
    artist: str = "Khruangbin",
    reason: str = "Warm psychedelic funk guitar with hypnotic grooves.",
) -> Recommendation:
    return Recommendation(
        concert=Concert(
            id=concert_id,
            name=f"{artist} Live",
            url=f"https://tickets.example/{concert_id}",
            artists=[Artist(name=artist)],
            date=NOW.date() + dt.timedelta(days=30),
            time=dt.time(20, 0),
            time_zone="America/Chicago",
            venue="Thalia Hall",
            city="Chicago",
            region="IL",
        ),
        reason=reason,
    )


class SavedSearchStack:
    """In-memory Supabase + Resend stub covering Alerts and Saved Searches."""

    def __init__(self) -> None:
        self.settings: dict[str, dict[str, Any]] = {}
        self.followed: list[dict[str, str]] = []
        self.followed_venues: list[dict[str, Any]] = []
        self.sent: list[dict[str, str]] = []
        self.saved_concerts: list[dict[str, Any]] = []
        self.sale_reminders_sent: list[dict[str, str]] = []
        self.saved_searches: list[dict[str, Any]] = []
        self.saved_search_sent: list[dict[str, str]] = []
        self.users: dict[str, dict[str, Any]] = {}
        self.emails: list[tuple[dict[str, Any], httpx.Headers]] = []
        self.resend_status = 200

    def person(self, user_id: str, email: str, *, confirmed: bool = True) -> None:
        self.users[user_id] = {
            "email": email,
            "email_confirmed_at": "2026-11-01T00:00:00Z" if confirmed else None,
        }

    def alerts_on(self, user_id: str, place: Place, *follows: str) -> None:
        self.settings[user_id] = {
            "place": place.model_dump(mode="json"),
            "enabled": True,
            "sale_reminders_enabled": False,
            "saved_searches_paused": False,
            "timezone": None,
        }
        for name in follows:
            self.followed.append(
                {"user_id": user_id, "artist_key": alerts.normalize(name), "name": name}
            )

    def add_saved_search(
        self,
        user_id: str,
        query_text: str,
        reading: Reading,
        *,
        last_run_at: dt.datetime | None = None,
        search_id: str | None = None,
    ) -> str:
        sid = search_id or str(uuid.uuid4())
        self.saved_searches.append(
            {
                "id": sid,
                "user_id": user_id,
                "query_text": query_text,
                "reading": reading.model_dump(mode="json", exclude_none=True),
                "last_run_at": last_run_at.isoformat() if last_run_at else None,
                "created_at": NOW.isoformat(),
            }
        )
        return sid

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.resend.com":
            self.emails.append((json.loads(request.content), request.headers))
            return httpx.Response(self.resend_status, json={"id": "email"})
        path, query = request.url.path, parse_qs(request.url.query.decode())
        if path.startswith("/auth/v1/admin/users/"):
            user = self.users.get(path.rsplit("/", 1)[1])
            return httpx.Response(200, json=user) if user else httpx.Response(404)
        if path == "/rest/v1/alert_settings":
            if request.method == "GET":
                if query.get("saved_searches_paused") == ["is.true"]:
                    wanted = query["user_id"][0].removeprefix("in.(").removesuffix(")").split(",")
                    rows = [
                        {"user_id": u}
                        for u, s in self.settings.items()
                        if u in wanted and s.get("saved_searches_paused")
                    ]
                    return httpx.Response(200, json=rows)
                rows = [
                    {"user_id": u} | s
                    for u, s in self.settings.items()
                    if s.get("enabled") or s.get("sale_reminders_enabled")
                ]
                return httpx.Response(200, json=rows)
            if request.method == "POST":
                for row in json.loads(request.content):
                    uid = row["user_id"]
                    self.settings.setdefault(
                        uid,
                        {
                            "place": None,
                            "enabled": False,
                            "sale_reminders_enabled": False,
                            "saved_searches_paused": False,
                            "timezone": None,
                        },
                    )
                    self.settings[uid] |= {k: v for k, v in row.items() if k != "user_id"}
                return httpx.Response(201)
        if path == "/rest/v1/saved_searches":
            if request.method == "GET":
                return httpx.Response(200, json=list(self.saved_searches))
            if request.method == "PATCH":
                ids = query["id"][0].removeprefix("in.(").removesuffix(")").split(",")
                patch = json.loads(request.content)
                for row in self.saved_searches:
                    if row["id"] in ids:
                        row["last_run_at"] = patch["last_run_at"]
                return httpx.Response(204)
            if request.method == "DELETE":
                target = query["id"][0].removeprefix("eq.")
                self.saved_searches = [r for r in self.saved_searches if r["id"] != target]
                self.saved_search_sent = [
                    r for r in self.saved_search_sent if r["saved_search_id"] != target
                ]
                return httpx.Response(204)
        if path == "/rest/v1/saved_search_sent":
            if request.method == "POST":
                for row in json.loads(request.content):
                    if not any(
                        r["saved_search_id"] == row["saved_search_id"]
                        and r["concert_id"] == row["concert_id"]
                        for r in self.saved_search_sent
                    ):
                        self.saved_search_sent.append(row)
                return httpx.Response(201)
            wanted = query["saved_search_id"][0].removeprefix("in.(").removesuffix(")").split(",")
            return httpx.Response(
                200, json=[r for r in self.saved_search_sent if r["saved_search_id"] in wanted]
            )
        tables: dict[str, list[dict[str, Any]]] = {
            "/rest/v1/followed_artists": self.followed,
            "/rest/v1/followed_venues": self.followed_venues,
            "/rest/v1/alerts_sent": self.sent,
            "/rest/v1/saved_concerts": self.saved_concerts,
            "/rest/v1/sale_reminders_sent": self.sale_reminders_sent,
        }
        if path in tables:
            table = tables[path]
            if request.method == "POST":
                table.extend(json.loads(request.content))
                return httpx.Response(201)
            wanted = query["user_id"][0].removeprefix("in.(").removesuffix(")").split(",")
            return httpx.Response(200, json=[r for r in table if r["user_id"] in wanted])
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")


async def _run_alerts(
    stack: SavedSearchStack,
    monkeypatch: pytest.MonkeyPatch,
    recs_by_place: dict[str, list[Recommendation]],
    *,
    now: dt.datetime = NOW,
    redis: FakeAsyncRedis | None = None,
    ran_places: list[str] | None = None,
) -> alerts.Outcome:
    async def find_concerts(*_: Any, **__: Any) -> list[Concert]:
        return CONCERTS

    async def fake_run_search(
        asked: str | Reading,
        imported: Any,
        near: Any,
        time_zone: str,
        services: Any,
    ) -> AsyncIterator[Any]:
        assert isinstance(asked, Reading)
        assert list(imported) == []
        assert near is None
        key = asked.place or (asked.artists[0] if asked.artists else "")
        if ran_places is not None:
            ran_places.append(key)
        await limits.record_spend(services.redis, Decimal("0.0012"))
        poster = Poster(recommendations=recs_by_place.get(key, []))
        yield ServerSentEvent(
            event="poster", data=poster.model_dump(mode="json", exclude_none=True)
        )
        yield ServerSentEvent(event="done", data={})

    monkeypatch.setattr(pool, "find_concerts", find_concerts)
    monkeypatch.setattr(pipeline, "run_search", fake_run_search)
    transport = httpx.MockTransport(stack.handle)
    services = make_services(
        settings_with(), transport, redis or FakeAsyncRedis(), contract_model()
    )
    async with (
        supabase.make_client(SUPABASE, transport) as accounts_client,
        resend.make_client("re_test", transport) as mail,
    ):
        return await alerts.run(
            services,
            accounts_client,
            SECRET,
            mail,
            "https://concertscout.test",
            "https://api.concertscout.test",
            now,
        )


def test_saved_search_request_rejects_coordinates_taste_and_spotify() -> None:
    # Extra top-level fields (near, taste, spotify) are refused.
    for extra in (
        {"near": {"lat": 41.88, "lon": -87.63}},
        {"taste": ["Khruangbin"]},
        {"spotify": {"artists": ["Khruangbin"]}},
    ):
        with pytest.raises(ValueError):
            saved_searches.SaveSearchRequest.model_validate(
                {"query_text": "Khruangbin in Chicago", "reading": {"place": "Chicago"}} | extra
            )

    # Extra fields inside reading (lat/lon/spotify) are refused.
    with pytest.raises(ValueError):
        saved_searches.SaveSearchRequest.model_validate(
            {
                "query_text": "Chicago",
                "reading": {"place": "Chicago", "lat": 41.88, "lon": -87.63},
            }
        )

    # Synthetic "Near you" place or empty reading with neither place nor artists is refused.
    with pytest.raises(ValueError):
        saved_searches.SaveSearchRequest.model_validate(
            {"query_text": "near me", "reading": {"place": "Near you"}}
        )
    with pytest.raises(ValueError):
        saved_searches.SaveSearchRequest.model_validate(
            {"query_text": "dreamy guitar", "reading": {"descriptors": ["dreamy guitar"]}}
        )


async def test_weekly_rerun_folds_unseen_recommendations_into_single_daily_alert_and_never_repeats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = SavedSearchStack()
    stack.person(ALICE, "alice@example.com")
    stack.alerts_on(ALICE, PLACE, "Contract Artist")
    sid = stack.add_saved_search(
        ALICE,
        "Something like Khruangbin in Chicago",
        Reading(artists=["Khruangbin"], place="Chicago"),
    )
    rec1 = _rec(
        "ss-rec-1", artist="Glass Beams", reason="Masked Melbourne trio playing psych funk."
    )

    outcome = await _run_alerts(stack, monkeypatch, {"Chicago": [rec1]}, now=NOW)

    assert outcome.sent == 1
    assert len(stack.emails) == 1
    [(email, headers)] = stack.emails
    assert email["to"] == ["alice@example.com"]
    assert "Saved Search pick" in email["subject"]
    assert "Contract Artist" in email["text"]
    assert "Saved Search: Something like Khruangbin in Chicago" in email["text"]
    assert "Glass Beams" in email["text"]
    assert rec1.reason in email["text"]
    assert rec1.concert.url in email["text"]
    assert rec1.reason in email["html"]
    assert rec1.concert.url in email["html"]
    assert headers["Idempotency-Key"] == f"alert-{ALICE}-{NOW.date()}"
    assert stack.saved_search_sent == [
        {"user_id": ALICE, "saved_search_id": sid, "concert_id": "ss-rec-1"}
    ]
    assert stack.saved_searches[0]["last_run_at"] == NOW.isoformat()

    # 3 days later: not due yet, so pipeline does not run and nothing is sent.
    ran: list[str] = []
    midweek = NOW + dt.timedelta(days=3)
    assert (
        await _run_alerts(stack, monkeypatch, {"Chicago": [rec1]}, now=midweek, ran_places=ran)
    ).sent == 0
    assert ran == []

    # 7 days later: due again. Only rec2 is new; rec1 NEVER repeats!
    next_week = NOW + dt.timedelta(days=7)
    rec2 = _rec("ss-rec-2", artist="Hermanos Gutierrez", reason="Desert instrumental guitar duo.")
    outcome2 = await _run_alerts(
        stack, monkeypatch, {"Chicago": [rec1, rec2]}, now=next_week, ran_places=ran
    )
    assert ran == ["Chicago"]
    assert outcome2.sent == 1
    assert len(stack.emails) == 2
    second_email = stack.emails[1][0]
    assert "Hermanos Gutierrez" in second_email["text"]
    assert rec2.reason in second_email["text"]
    assert "Glass Beams" not in second_email["text"]

    # Another 7 days later with no new Recommendations: advances last_run_at and sends no email.
    week3 = NOW + dt.timedelta(days=14)
    outcome3 = await _run_alerts(stack, monkeypatch, {"Chicago": [rec1, rec2]}, now=week3)
    assert outcome3.sent == 0
    assert len(stack.emails) == 2
    assert stack.saved_searches[0]["last_run_at"] == week3.isoformat()


async def test_spend_cap_stops_saved_search_reruns_first_and_defers_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeAsyncRedis()
    # Set daily spend right at the Saved Search headroom boundary ($0.75 of $1.00 daily cap).
    await limits.record_spend(redis, limits.DAILY_SPEND - limits.SAVED_SEARCH_DAILY_HEADROOM)
    # Live visitor check_spend STILL passes (headroom preserved for live visitors!).
    await limits.check_spend(redis)

    stack = SavedSearchStack()
    stack.person(ALICE, "alice@example.com")
    stack.add_saved_search(ALICE, "Jazz in Austin", Reading(genres=["Jazz"], place="Austin"))
    ran: list[str] = []

    outcome = await _run_alerts(
        stack,
        monkeypatch,
        {"Austin": [_rec("austin-1", artist="Kamasi Washington")]},
        now=NOW,
        redis=redis,
        ran_places=ran,
    )

    assert ran == []
    assert outcome.sent == 0
    assert stack.emails == []
    # Skipped rerun leaves last_run_at untouched so it waits cleanly for the next eligible run.
    assert stack.saved_searches[0]["last_run_at"] is None

    # Same rule for monthly spend headroom ($8.50 of $10.00 monthly cap).
    monthly_redis = FakeAsyncRedis()
    await limits.record_spend(
        monthly_redis, limits.MONTHLY_SPEND - limits.SAVED_SEARCH_MONTHLY_HEADROOM
    )
    with pytest.raises(limits.SpendCapReached):
        await limits.check_saved_search_spend(monthly_redis)


async def test_failed_resend_does_not_mark_saved_search_recommendations_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = SavedSearchStack()
    stack.person(ALICE, "alice@example.com")
    stack.add_saved_search(
        ALICE, "Khruangbin in Chicago", Reading(artists=["Khruangbin"], place="Chicago")
    )
    stack.resend_status = 500

    outcome = await _run_alerts(stack, monkeypatch, {"Chicago": [_rec("fail-1")]}, now=NOW)

    assert outcome.sent == 0
    assert stack.saved_search_sent == []
    assert stack.saved_searches[0]["last_run_at"] is None


async def test_unsubscribe_pauses_saved_search_reruns(monkeypatch: pytest.MonkeyPatch) -> None:
    stack = SavedSearchStack()
    stack.person(ALICE, "alice@example.com")
    stack.add_saved_search(
        ALICE, "Khruangbin in Chicago", Reading(artists=["Khruangbin"], place="Chicago")
    )

    # One-click unsubscribe pauses Saved Search Alerts even without an alert_settings row.
    app = create_app(
        settings_with(
            supabase_url=SUPABASE,
            supabase_publishable_key="publishable",
            supabase_secret_key=SECRET,
            resend_api_key=SecretStr("re_test"),
        ),
        httpx.MockTransport(stack.handle),
        FakeAsyncRedis(),
        contract_model(),
    )
    token = alerts.unsubscribe_token(SECRET, ALICE)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="https://api.test"
    ) as api:
        res = await api.post("/alerts/unsubscribe", params={"account": ALICE, "token": token})
    assert res.status_code == 204
    assert stack.settings[ALICE]["saved_searches_paused"] is True

    ran: list[str] = []
    outcome = await _run_alerts(
        stack, monkeypatch, {"Chicago": [_rec("paused-1")]}, now=NOW, ran_places=ran
    )
    assert ran == []
    assert outcome.sent == 0
    assert stack.emails == []


# --- Real Supabase stack tests (CRUD, 5-cap, RLS isolation, cascade deletion) ---


@pytest.fixture
async def supabase_api(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    install_sources(monkeypatch)
    app = create_app(
        settings_with(
            supabase_url=sb_stack.URL,
            supabase_publishable_key=sb_stack.PUBLISHABLE_KEY,
            supabase_secret_key=SecretStr(sb_stack.secret_key()),
        ),
        sb_stack.stack_transport(httpx.MockTransport(forbidden_http)),
        FakeAsyncRedis(),
        contract_model(),
    )
    transport = httpx.ASGITransport(app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        yield client


def _bearer(person: sb_stack.Person) -> dict[str, str]:
    return {"Authorization": f"Bearer {person.token}", "Origin": ORIGIN}


@pytest.mark.supabase
async def test_saved_searches_crud_cap_rls_and_cascade(
    supabase_api: httpx.AsyncClient,
) -> None:
    owner, other = sb_stack.new_person(), sb_stack.new_person()

    # Rejects coordinates / Taste / Spotify fields.
    bad = await supabase_api.post(
        "/account/saved-searches",
        json={
            "query_text": "Khruangbin in Chicago",
            "reading": {"artists": ["Khruangbin"], "place": "Chicago"},
            "near": {"lat": 41.88, "lon": -87.63},
        },
        headers=_bearer(owner),
    )
    assert bad.status_code == 422
    assert bad.json()["code"] == "invalid_saved_search"

    # Create 5 Saved Searches; duplicate save returns the same row without consuming a slot.
    created_ids: list[str] = []
    for city in ("Chicago", "Austin", "Seattle", "Denver", "Boston"):
        resp = await supabase_api.post(
            "/account/saved-searches",
            json={
                "query_text": f"Khruangbin in {city}",
                "reading": {"artists": ["Khruangbin"], "place": city},
            },
            headers=_bearer(owner),
        )
        assert resp.status_code == 200
        created_ids.append(resp.json()["id"])

    dup = await supabase_api.post(
        "/account/saved-searches",
        json={
            "query_text": "khruangbin in chicago",
            "reading": {"artists": ["Khruangbin"], "place": "Chicago"},
        },
        headers=_bearer(owner),
    )
    assert dup.status_code == 200
    assert dup.json()["id"] == created_ids[0]

    # 6th Saved Search is refused with 409 saved_search_limit.
    sixth = await supabase_api.post(
        "/account/saved-searches",
        json={
            "query_text": "Khruangbin in Miami",
            "reading": {"artists": ["Khruangbin"], "place": "Miami"},
        },
        headers=_bearer(owner),
    )
    assert sixth.status_code == 409
    assert sixth.json()["code"] == "saved_search_limit"

    # Owner lists all 5; another Account sees none and cannot delete or insert rows directly.
    listed = (await supabase_api.get("/account/saved-searches", headers=_bearer(owner))).json()
    assert len(listed) == 5

    other_list = (await supabase_api.get("/account/saved-searches", headers=_bearer(other))).json()
    assert other_list == []

    # RLS prevents `other` from deleting `owner`'s Saved Search, inserting into saved_searches,
    # or accessing saved_search_sent.
    await supabase_api.delete(f"/account/saved-searches/{created_ids[0]}", headers=_bearer(other))
    still_five = (await supabase_api.get("/account/saved-searches", headers=_bearer(owner))).json()
    assert len(still_five) == 5

    with sb_stack.rest(other.token) as rest:
        assert rest.post(
            "/saved_searches",
            json={"user_id": owner.id, "query_text": "forged", "reading": {"place": "Chicago"}},
        ).status_code in (401, 403)
        assert rest.get("/saved_search_sent", params={"select": "concert_id"}).status_code in (
            401,
            403,
        )

    # Record a sent concert for created_ids[0], then delete it -> cascades saved_search_sent.
    secret = SecretStr(sb_stack.secret_key())
    transport = sb_stack.stack_transport(httpx.MockTransport(forbidden_http))
    async with supabase.make_client(sb_stack.URL, transport) as client:
        await supabase.record_saved_search_sent(client, secret, owner.id, [(created_ids[0], "c-1")])
        assert await supabase.saved_search_sent_for(client, secret, [created_ids[0]]) == {
            created_ids[0]: {"c-1"}
        }

        deleted = await supabase_api.delete(
            f"/account/saved-searches/{created_ids[0]}", headers=_bearer(owner)
        )
        assert deleted.status_code == 204
        assert await supabase.saved_search_sent_for(client, secret, [created_ids[0]]) == {}

        # Deleting the Account cascades all remaining Saved Searches and sent records.
        await supabase.record_saved_search_sent(client, secret, owner.id, [(created_ids[1], "c-2")])
        account = supabase.Account(owner.id, owner.token, 0)
        await supabase.delete_user(client, secret, account)
        assert await supabase.saved_search_sent_for(client, secret, [created_ids[1]]) == {}
        due = await supabase.due_saved_searches(client, secret, NOW)
        assert all(item.user_id != owner.id for item in due)
