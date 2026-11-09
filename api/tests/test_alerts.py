"""Alerts: who gets an email, what it says, and that nothing is sent twice or lost (ADR 0006).

Supabase and Resend are substituted at the HTTP boundary, and the pool at its typed boundary.
"""

import datetime as dt
import json
from collections.abc import Sequence
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from pydantic import SecretStr

from concert_scout import alerts, pool
from concert_scout.app import create_app, make_services
from concert_scout.models import Concert, Place
from concert_scout.sources import resend, supabase
from concert_scout.sources.supabase import FollowedArtist
from tests.contracts import CONCERTS, NOW, PLACE, contract_model, settings_with

SECRET = SecretStr("test-secret-key")
SUPABASE = "https://supabase.test"
ALICE, BOB = "00000000-0000-0000-0000-00000000000a", "00000000-0000-0000-0000-00000000000b"


class Stack:
    """Just enough of Supabase's Data API and Auth admin, and of Resend, for the Alert run."""

    def __init__(self) -> None:
        self.settings: dict[str, dict[str, Any]] = {}
        self.followed: list[dict[str, str]] = []
        self.sent: list[dict[str, str]] = []
        self.users: dict[str, dict[str, Any]] = {}
        self.emails: list[tuple[dict[str, Any], httpx.Headers]] = []
        self.resend_status = 200

    def person(self, user_id: str, email: str, *, confirmed: bool = True) -> None:
        self.users[user_id] = {
            "email": email,
            "email_confirmed_at": "2026-11-01T00:00:00Z" if confirmed else None,
        }

    def alerts_on(self, user_id: str, place: Place, *follows: str) -> None:
        self.settings[user_id] = {"place": place.model_dump(mode="json"), "enabled": True}
        for name in follows:
            self.followed.append(
                {"user_id": user_id, "artist_key": alerts.normalize(name), "name": name}
            )

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.resend.com":
            self.emails.append((json.loads(request.content), request.headers))
            return httpx.Response(self.resend_status, json={"id": "email"})
        path, query = request.url.path, parse_qs(request.url.query.decode())
        if path.startswith("/auth/v1/admin/users/"):
            user = self.users.get(path.rsplit("/", 1)[1])
            return httpx.Response(200, json=user) if user else httpx.Response(404)
        if path == "/rest/v1/alert_settings" and request.method == "GET":
            rows = [{"user_id": u} | s for u, s in self.settings.items() if s["enabled"]]
            return httpx.Response(200, json=rows)
        if path == "/rest/v1/alert_settings" and request.method == "PATCH":
            user = query["user_id"][0].removeprefix("eq.")
            if user in self.settings:
                self.settings[user] |= {"enabled": json.loads(request.content)["enabled"]}
            return httpx.Response(204)
        if path == "/rest/v1/alert_settings" and request.method == "POST":
            for row in json.loads(request.content):
                self.settings.setdefault(row["user_id"], {"place": None, "enabled": False})
                self.settings[row["user_id"]] |= {
                    k: v for k, v in row.items() if k in ("place", "enabled")
                }
            return httpx.Response(201)
        if path in ("/rest/v1/followed_artists", "/rest/v1/alerts_sent"):
            table = self.followed if "followed" in path else self.sent
            if request.method == "POST":
                table.extend(json.loads(request.content))
                return httpx.Response(201)
            wanted = query["user_id"][0].removeprefix("in.(").removesuffix(")").split(",")
            return httpx.Response(200, json=[r for r in table if r["user_id"] in wanted])
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")


@pytest.fixture
def stack(monkeypatch: pytest.MonkeyPatch) -> Stack:
    async def find_concerts(*_: Any, **__: Any) -> list[Concert]:
        return CONCERTS

    monkeypatch.setattr(pool, "find_concerts", find_concerts)
    return Stack()


async def run(stack: Stack, redis: FakeAsyncRedis | None = None) -> alerts.Outcome:
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
            NOW,
        )


async def test_an_alert_lists_new_concerts_by_followed_artists_from_source_facts(
    stack: Stack,
) -> None:
    stack.person(ALICE, "alice@example.com")
    stack.person(BOB, "bob@example.com")
    stack.alerts_on(ALICE, PLACE, "contract artist")
    stack.alerts_on(BOB, PLACE, "Nobody Playing")

    outcome = await run(stack)

    assert (outcome.accounts, outcome.places, outcome.sent) == (2, 1, 1)
    [(email, headers)] = stack.emails
    assert email["to"] == ["alice@example.com"]
    assert email["from"] == resend.ALERT_SENDER
    assert email["subject"] == "2 new Concerts from Artists you follow"
    text = email["text"]
    one, three = CONCERTS[0], CONCERTS[2]
    assert one.date and three.date
    assert f"{one.date:%a, %b} {one.date.day}, {one.date.year} at 7:30 PM" in text
    assert "Source Hall, San Francisco, CA" in text and f"Tickets: {one.url}" in text
    assert f"Tickets: {three.url}" in text
    assert "Second Contract Artist" not in text
    # The Concert with no time shows only its date. Nothing is invented.
    assert f"{three.date.day}, {three.date.year}\nThird Hall" in text
    assert headers["Idempotency-Key"] == f"alert-{ALICE}-{NOW.date()}"
    assert email["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert sorted(r["concert_id"] for r in stack.sent) == [one.id, three.id]


async def test_a_concert_is_never_sent_twice(stack: Stack) -> None:
    stack.person(ALICE, "alice@example.com")
    stack.alerts_on(ALICE, PLACE, "Contract Artist")

    await run(stack)
    again = await run(stack)

    assert again.sent == 0
    assert len(stack.emails) == 1


async def test_a_failed_send_records_nothing_so_tomorrow_tries_again(stack: Stack) -> None:
    stack.person(ALICE, "alice@example.com")
    stack.alerts_on(ALICE, PLACE, "Contract Artist")
    stack.resend_status = 500

    outcome = await run(stack)

    assert outcome.sent == 0
    assert stack.sent == []


async def test_an_unconfirmed_address_gets_nothing(stack: Stack) -> None:
    stack.person(ALICE, "alice@example.com", confirmed=False)
    stack.alerts_on(ALICE, PLACE, "Contract Artist")

    assert (await run(stack)).sent == 0
    assert stack.emails == []


async def test_the_daily_limit_stops_sending(stack: Stack, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(alerts, "DAILY_EMAILS", 1)
    for user, address in ((ALICE, "alice@example.com"), (BOB, "bob@example.com")):
        stack.person(user, address)
        stack.alerts_on(user, PLACE, "Contract Artist")

    assert (await run(stack)).sent == 1
    assert len(stack.emails) == 1


async def test_a_second_run_waits_for_the_first(stack: Stack) -> None:
    redis = FakeAsyncRedis()
    await redis.set(alerts.LOCK, "another run")
    stack.person(ALICE, "alice@example.com")
    stack.alerts_on(ALICE, PLACE, "Contract Artist")

    outcome = await run(stack, redis)

    assert outcome.error == "alerts already running"
    assert stack.emails == []


def test_one_concert_names_its_artist_and_city() -> None:
    assert alerts.subject([CONCERTS[0]]) == "Contract Artist has a new Concert in San Francisco"


def test_the_time_reads_on_the_venues_clock_with_its_zone() -> None:
    concert = CONCERTS[0].model_copy(
        update={
            "date": dt.date(2027, 1, 15),
            "time": dt.time(19, 30),
            "time_zone": "America/Chicago",
        }
    )
    assert alerts.when(concert) == "Fri, Jan 15, 2027 at 7:30 PM CST"


def test_matching_reads_lineup_names_in_code() -> None:
    followed = [FollowedArtist(artist_key=alerts.normalize("CONTRACT  ARTIST"), name="x")]
    found: Sequence[Concert] = alerts.matching(list(reversed(CONCERTS)), followed)
    assert [c.id for c in found] == ["contract-one", "contract-three"]


def unsubscribe_app(stack: Stack) -> httpx.AsyncClient:
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
    return httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://api.test")


async def test_the_signed_link_turns_alerts_off_without_a_sign_in(stack: Stack) -> None:
    stack.alerts_on(ALICE, PLACE, "Contract Artist")
    token = alerts.unsubscribe_token(SECRET, ALICE)

    async with unsubscribe_app(stack) as api:
        # Mail apps post the one-click body to the link from the List-Unsubscribe header.
        response = await api.post(
            "/alerts/unsubscribe",
            params={"account": ALICE, "token": token},
            content="List-Unsubscribe=One-Click",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    assert response.status_code == 204
    assert stack.settings[ALICE]["enabled"] is False


async def test_a_forged_link_changes_nothing(stack: Stack) -> None:
    stack.alerts_on(ALICE, PLACE, "Contract Artist")
    forged = alerts.unsubscribe_token(SECRET, BOB)

    async with unsubscribe_app(stack) as api:
        response = await api.post("/alerts/unsubscribe", params={"account": ALICE, "token": forged})

    assert response.status_code == 403
    assert stack.settings[ALICE]["enabled"] is True


async def test_the_alert_email_links_to_the_unsubscribe_page_and_one_click_api(
    stack: Stack,
) -> None:
    stack.person(ALICE, "alice@example.com")
    stack.alerts_on(ALICE, PLACE, "Contract Artist")

    await run(stack)

    [(email, _)] = stack.emails
    one_click: str = email["headers"]["List-Unsubscribe"].strip("<>")
    assert urlsplit(one_click).netloc == "api.concertscout.test"
    page = next(line for line in email["text"].splitlines() if line.startswith("Stop these"))
    assert "https://concertscout.test/unsubscribe?" in page
    query = parse_qs(urlsplit(one_click).query)
    assert alerts.valid_token(SECRET, query["account"][0], query["token"][0])
