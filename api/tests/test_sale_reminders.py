"""Saved Concert sale reminders: selection, time-zone formatting, folding, and RLS (Issue #88)."""

import datetime as dt
import json
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from pydantic import SecretStr

from concert_scout import alerts, pool
from concert_scout.app import create_app, make_services
from concert_scout.models import Artist, Concert, Place, Presale
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


def _saved_concert(
    concert_id: str = "saved-one",
    *,
    artist: str = "Saved Artist",
    general_sale: dt.datetime | None = None,
    presales: list[Presale] | None = None,
) -> Concert:
    return Concert(
        id=concert_id,
        name=f"{artist} Live",
        url=f"https://tickets.example/{concert_id}",
        artists=[Artist(name=artist)],
        date=NOW.date() + dt.timedelta(days=45),
        time=dt.time(20, 0),
        time_zone="America/Los_Angeles",
        venue="Fox Theater",
        city="Oakland",
        region="CA",
        general_sale=general_sale,
        presales=presales or [],
    )


class ReminderStack:
    """In-memory Supabase + Resend stub covering both followed Alerts and sale reminders."""

    def __init__(self) -> None:
        self.settings: dict[str, dict[str, Any]] = {}
        self.followed: list[dict[str, str]] = []
        self.followed_venues: list[dict[str, Any]] = []
        self.sent: list[dict[str, str]] = []
        self.saved_concerts: list[dict[str, Any]] = []
        self.sale_reminders_sent: list[dict[str, str]] = []
        self.users: dict[str, dict[str, Any]] = {}
        self.emails: list[tuple[dict[str, Any], httpx.Headers]] = []
        self.resend_status = 200

    def person(self, user_id: str, email: str, *, confirmed: bool = True) -> None:
        self.users[user_id] = {
            "email": email,
            "email_confirmed_at": "2026-11-01T00:00:00Z" if confirmed else None,
        }

    def configure(
        self,
        user_id: str,
        *,
        place: Place | None = None,
        enabled: bool = False,
        sale_reminders_enabled: bool = False,
        timezone: str | None = None,
        follows: tuple[str, ...] = (),
    ) -> None:
        self.settings[user_id] = {
            "place": place.model_dump(mode="json") if place else None,
            "enabled": enabled,
            "sale_reminders_enabled": sale_reminders_enabled,
            "timezone": timezone,
        }
        for name in follows:
            self.followed.append(
                {"user_id": user_id, "artist_key": alerts.normalize(name), "name": name}
            )

    def save_concert(self, user_id: str, concert: Concert) -> None:
        self.saved_concerts.append(
            {
                "user_id": user_id,
                "concert_id": concert.id,
                "concert": concert.model_dump(mode="json", exclude_none=True),
            }
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
            rows = [
                {"user_id": u} | s
                for u, s in self.settings.items()
                if s["enabled"] or s["sale_reminders_enabled"]
            ]
            return httpx.Response(200, json=rows)
        if path == "/rest/v1/alert_settings" and request.method == "PATCH":
            user = query["user_id"][0].removeprefix("eq.")
            if user in self.settings:
                patch = json.loads(request.content)
                for key in ("enabled", "sale_reminders_enabled", "timezone"):
                    if key in patch:
                        self.settings[user][key] = patch[key]
            return httpx.Response(204)
        if path == "/rest/v1/saved_searches" and request.method == "GET":
            return httpx.Response(200, json=[])
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


async def _run(
    stack: ReminderStack,
    monkeypatch: pytest.MonkeyPatch,
    now: dt.datetime = NOW,
) -> alerts.Outcome:
    async def find_concerts(*_: Any, **__: Any) -> list[Concert]:
        return CONCERTS

    monkeypatch.setattr(pool, "find_concerts", find_concerts)
    transport = httpx.MockTransport(stack.handle)
    services = make_services(settings_with(), transport, FakeAsyncRedis(), contract_model())
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


async def test_presale_within_36h_appears_formatted_in_accounts_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = ReminderStack()
    stack.person(ALICE, "alice@example.com")
    stack.configure(ALICE, sale_reminders_enabled=True, timezone="America/New_York")
    # 2027-01-15 15:00 UTC is 10:00 AM EST in America/New_York.
    now = dt.datetime(2027, 1, 14, 14, 0, tzinfo=dt.UTC)
    presale_start = dt.datetime(2027, 1, 15, 15, 0, tzinfo=dt.UTC)
    concert = _saved_concert(
        general_sale=dt.datetime(2027, 1, 18, 15, 0, tzinfo=dt.UTC),
        presales=[
            Presale(
                name="Artist Presale",
                start=presale_start,
                end=presale_start + dt.timedelta(hours=24),
            )
        ],
    )
    stack.save_concert(ALICE, concert)

    outcome = await _run(stack, monkeypatch, now=now)

    assert outcome.sent == 1
    assert outcome.places == 0
    [(email, headers)] = stack.emails
    assert email["to"] == ["alice@example.com"]
    assert email["subject"] == "Saved Artist goes on sale soon"
    assert "Artist Presale opens Fri, Jan 15, 2027 at 10:00 AM EST" in email["text"]
    assert "Artist Presale opens Fri, Jan 15, 2027 at 10:00 AM EST" in email["html"]
    assert concert.url in email["text"] and concert.url in email["html"]
    assert headers["Idempotency-Key"] == f"alert-{ALICE}-{now.date()}"
    assert len(stack.sale_reminders_sent) == 1
    assert stack.sale_reminders_sent[0]["concert_id"] == concert.id
    assert stack.sale_reminders_sent[0]["sale_key"].startswith("presale:artist presale:")


async def test_presale_and_later_general_sale_each_remind_once_in_their_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = ReminderStack()
    stack.person(ALICE, "alice@example.com")
    stack.configure(ALICE, sale_reminders_enabled=True, timezone="America/Los_Angeles")
    day1 = dt.datetime(2027, 1, 13, 14, 0, tzinfo=dt.UTC)
    presale_start = dt.datetime(2027, 1, 14, 18, 0, tzinfo=dt.UTC)  # 10:00 AM PST
    general_start = dt.datetime(2027, 1, 16, 18, 0, tzinfo=dt.UTC)  # 10:00 AM PST
    concert = _saved_concert(
        general_sale=general_start,
        presales=[
            Presale(
                name="Live Nation Presale",
                start=presale_start,
                end=presale_start + dt.timedelta(hours=24),
            )
        ],
    )
    stack.save_concert(ALICE, concert)

    # Day 1: presale is 28h away (inside 36h), general sale is 76h away (outside 36h).
    assert (await _run(stack, monkeypatch, now=day1)).sent == 1
    assert (
        "Live Nation Presale opens Thu, Jan 14, 2027 at 10:00 AM PST" in stack.emails[0][0]["text"]
    )

    # Re-running the same day sends nothing (presale already recorded).
    assert (await _run(stack, monkeypatch, now=day1 + dt.timedelta(hours=2))).sent == 0

    # Day 3: presale has passed, general sale is 28h away -> reminds once about general sale.
    day3 = dt.datetime(2027, 1, 15, 14, 0, tzinfo=dt.UTC)
    assert (await _run(stack, monkeypatch, now=day3)).sent == 1
    assert "General sale opens Sat, Jan 16, 2027 at 10:00 AM PST" in stack.emails[1][0]["text"]

    # Re-running later on Day 3 sends nothing (general sale already recorded).
    assert (await _run(stack, monkeypatch, now=day3 + dt.timedelta(hours=4))).sent == 0
    assert len(stack.emails) == 2


def test_vip_opened_far_away_and_already_reminded_sales_are_excluded() -> None:
    now = dt.datetime(2027, 1, 14, 12, 0, tzinfo=dt.UTC)
    soon = now + dt.timedelta(hours=20)
    far = now + dt.timedelta(hours=36, minutes=1)
    past = now - dt.timedelta(minutes=5)

    # VIP package presales are excluded even if they open within 36h.
    vip_only = _saved_concert(
        "vip-only",
        general_sale=far,
        presales=[
            Presale(name="VIP Package Presale", start=soon, end=soon + dt.timedelta(hours=12)),
            Presale(name="Artist VIP Packages", start=soon, end=soon + dt.timedelta(hours=12)),
        ],
    )
    assert alerts.next_sale_reminder(vip_only, now, set()) is None

    # Already-opened presale (<= now) is excluded.
    opened_presale = _saved_concert(
        "opened-presale",
        general_sale=far,
        presales=[Presale(name="Artist Presale", start=past, end=soon)],
    )
    assert alerts.next_sale_reminder(opened_presale, now, set()) is None

    # Exact boundary: sale at now is excluded; sale at now + 36h is included.
    at_now = _saved_concert("at-now", general_sale=now)
    at_boundary = _saved_concert("at-boundary", general_sale=now + dt.timedelta(hours=36))
    assert alerts.next_sale_reminder(at_now, now, set()) is None
    boundary_reminder = alerts.next_sale_reminder(at_boundary, now, set())
    assert boundary_reminder is not None and boundary_reminder.sale_label == "General sale"

    # Once general sale has opened, no presale reminders fire.
    on_general = _saved_concert(
        "on-general",
        general_sale=past,
        presales=[Presale(name="Late Presale", start=soon, end=soon + dt.timedelta(hours=5))],
    )
    assert alerts.next_sale_reminder(on_general, now, set()) is None

    # Already-reminded sale is excluded.
    reminded_set = {(at_boundary.id, boundary_reminder.sale_key)}
    assert alerts.next_sale_reminder(at_boundary, now, reminded_set) is None


async def test_sale_reminders_fold_into_the_same_daily_alert_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = ReminderStack()
    stack.person(ALICE, "alice@example.com")
    stack.configure(
        ALICE,
        place=PLACE,
        enabled=True,
        sale_reminders_enabled=True,
        timezone="America/Chicago",
        follows=("Contract Artist",),
    )
    concert = _saved_concert(general_sale=NOW + dt.timedelta(hours=24))
    stack.save_concert(ALICE, concert)

    outcome = await _run(stack, monkeypatch, now=NOW)

    assert outcome.sent == 1
    assert len(stack.emails) == 1
    [(email, headers)] = stack.emails
    assert email["subject"] == (
        "2 new Concerts from Artists you follow + 1 Saved Concert on sale soon"
    )
    assert "Contract Artist" in email["text"]
    assert "Saved Concerts going on sale:" in email["text"]
    assert "Saved Artist" in email["text"]
    assert "General sale opens" in email["text"]
    assert "Saved Concerts going on sale" in email["html"]
    assert "General sale opens" in email["html"]
    assert headers["Idempotency-Key"] == f"alert-{ALICE}-{NOW.date()}"
    assert len(stack.sent) == 2
    assert len(stack.sale_reminders_sent) == 1


async def test_failed_resend_does_not_mark_sale_reminded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = ReminderStack()
    stack.person(ALICE, "alice@example.com")
    stack.configure(ALICE, sale_reminders_enabled=True, timezone="America/Los_Angeles")
    stack.save_concert(ALICE, _saved_concert(general_sale=NOW + dt.timedelta(hours=12)))
    stack.resend_status = 500

    outcome = await _run(stack, monkeypatch, now=NOW)

    assert outcome.sent == 0
    assert stack.sale_reminders_sent == []


async def test_opted_out_account_gets_no_sale_reminders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = ReminderStack()
    stack.person(ALICE, "alice@example.com")
    stack.configure(ALICE, sale_reminders_enabled=False, timezone="America/Los_Angeles")
    stack.save_concert(ALICE, _saved_concert(general_sale=NOW + dt.timedelta(hours=12)))

    outcome = await _run(stack, monkeypatch, now=NOW)

    assert outcome.accounts == 0
    assert outcome.sent == 0
    assert stack.emails == []


# --- Real Supabase stack tests (RLS, validation, persistence, cascade) ---


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
async def test_sale_reminder_settings_validation_rls_and_cascade(
    supabase_api: httpx.AsyncClient,
) -> None:
    owner, other = sb_stack.new_person(), sb_stack.new_person()

    # Enabling without a time zone is refused.
    missing_tz = await supabase_api.put(
        "/account/alerts/sale-reminders", json={"enabled": True}, headers=_bearer(owner)
    )
    assert missing_tz.status_code == 409
    assert missing_tz.json()["code"] == "alert_timezone"

    # Invalid IANA time zone is refused.
    bad_tz = await supabase_api.put(
        "/account/alerts/sale-reminders",
        json={"enabled": True, "timezone": "Mars/Olympus"},
        headers=_bearer(owner),
    )
    assert bad_tz.status_code == 422

    # Valid IANA time zone enables and persists across sign-ins.
    enabled = await supabase_api.put(
        "/account/alerts/sale-reminders",
        json={"enabled": True, "timezone": "America/New_York"},
        headers=_bearer(owner),
    )
    assert enabled.status_code == 200
    assert enabled.json() == {"sale_reminders_enabled": True, "timezone": "America/New_York"}

    elsewhere = sb_stack.Person(owner.id, owner.email, sb_stack.sign_in(owner.email))
    view = (await supabase_api.get("/account/alerts", headers=_bearer(elsewhere))).json()
    assert view["sale_reminders_enabled"] is True
    assert view["timezone"] == "America/New_York"

    # Another Account cannot see owner's settings or write/read sent reminders directly.
    other_view = (await supabase_api.get("/account/alerts", headers=_bearer(other))).json()
    assert other_view["sale_reminders_enabled"] is False
    assert other_view["timezone"] is None
    with sb_stack.rest(other.token) as rest:
        assert rest.get("/sale_reminders_sent", params={"select": "concert_id"}).status_code in (
            401,
            403,
        )
        assert rest.post(
            "/sale_reminders_sent",
            json={"user_id": owner.id, "concert_id": "forged", "sale_key": "general:x"},
        ).status_code in (401, 403)

    # Real daily Alert run sends once, records in sale_reminders_sent, and deleting cascades.
    secret = SecretStr(sb_stack.secret_key())
    emails: list[dict[str, object]] = []

    def mail(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.resend.com"
        emails.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "email"})

    transport = sb_stack.stack_transport(httpx.MockTransport(mail))
    services = make_services(settings_with(), transport, FakeAsyncRedis(), contract_model())
    upcoming = _saved_concert(
        "sb-sale-concert",
        general_sale=NOW + dt.timedelta(hours=18),
    )
    async with (
        supabase.make_client(sb_stack.URL, transport) as client,
        resend.make_client("re_test", transport) as mail_client,
    ):
        account = supabase.Account(owner.id, owner.token, 0)
        await supabase.save(client, secret, account, [(upcoming, None)])

        async def alert_run() -> alerts.Outcome:
            return await alerts.run(
                services, client, secret, mail_client, "https://site.test", "https://api.test", NOW
            )

        await alert_run()
        await alert_run()

        mine = [e for e in emails if e["to"] == [owner.email]]
        assert len(mine) == 1
        sent = await supabase.sale_reminders_sent_to(client, secret, [owner.id])
        assert len(sent[owner.id]) == 1

        await supabase.delete_user(client, secret, account)
        assert await supabase.sale_reminders_sent_to(client, secret, [owner.id]) == {}
        assert owner.id not in [
            a.user_id for a in await supabase.accounts_with_alerts(client, secret)
        ]
