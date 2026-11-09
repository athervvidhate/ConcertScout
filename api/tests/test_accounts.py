"""Account ownership against the real local Supabase stack: Auth, the Data API and row policies.

Run `make supabase` first. Ticketmaster is substituted at its typed boundary, as elsewhere.
"""

import base64
import json
import time
from collections.abc import AsyncIterator

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from joserfc import jwt
from joserfc.jwk import ECKey
from pydantic import SecretStr

from concert_scout import accounts, pool
from concert_scout.app import create_app
from concert_scout.models import Concert
from concert_scout.sources import supabase
from tests import supabase_stack as stack
from tests.contracts import CONCERTS, contract_model, forbidden_http, install_sources, settings_with

pytestmark = pytest.mark.supabase

ORIGIN = "http://localhost:3000"
ONE, TWO = CONCERTS[0], CONCERTS[1]


@pytest.fixture(autouse=True)
def typed_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    install_sources(monkeypatch)


@pytest.fixture
async def api() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        settings_with(
            supabase_url=stack.URL,
            supabase_publishable_key=stack.PUBLISHABLE_KEY,
            supabase_secret_key=SecretStr(stack.secret_key()),
        ),
        stack.stack_transport(httpx.MockTransport(forbidden_http)),
        FakeAsyncRedis(),
        contract_model(),
    )
    transport = httpx.ASGITransport(app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        yield client


def bearer(person: stack.Person) -> dict[str, str]:
    return {"Authorization": f"Bearer {person.token}", "Origin": ORIGIN}


async def saved_ids(api: httpx.AsyncClient, person: stack.Person) -> list[str]:
    response = await api.get("/account/saved", headers=bearer(person))
    assert response.status_code == 200
    return [row["concert"]["id"] for row in response.json()]


async def test_a_save_holds_the_source_facts_and_follows_the_account(
    api: httpx.AsyncClient,
) -> None:
    person = stack.new_person()
    saved = await api.put(
        f"/account/saved/{ONE.id}", json={"reason": "A source-backed match"}, headers=bearer(person)
    )
    assert saved.status_code == 200

    # A second sign-in is a second device: a new token for the same account.
    elsewhere = stack.Person(person.id, person.email, stack.sign_in(person.email))
    response = await api.get("/account/saved", headers=bearer(elsewhere))
    assert response.json() == [
        {
            "concert": ONE.model_dump(mode="json", exclude_none=True),
            "reason": "A source-backed match",
        }
    ]


async def test_one_account_cannot_read_or_remove_another_accounts_saves(
    api: httpx.AsyncClient,
) -> None:
    owner, other = stack.new_person(), stack.new_person()
    await api.put(f"/account/saved/{ONE.id}", json={}, headers=bearer(owner))

    assert await saved_ids(api, other) == []
    removed = await api.delete(f"/account/saved/{ONE.id}", headers=bearer(other))
    assert removed.status_code == 204
    assert await saved_ids(api, owner) == [ONE.id]

    # Straight to the Data API with the public key, the row policies still hide the row.
    with stack.rest(other.token) as rest:
        assert rest.get("/saved_concerts", params={"select": "concert_id"}).json() == []


async def test_a_browser_cannot_write_facts_past_the_api(api: httpx.AsyncClient) -> None:
    person = stack.new_person()
    forged = {"user_id": person.id, "concert_id": "forged", "concert": {"name": "Not real"}}
    with stack.rest(person.token) as rest:
        written = rest.post("/saved_concerts", json=forged)
        assert written.status_code in (401, 403)
        assert rest.get("/saved_concerts", params={"select": "concert_id"}).json() == []
    assert await saved_ids(api, person) == []


async def test_importing_device_saves_twice_adds_each_concert_once(
    api: httpx.AsyncClient,
) -> None:
    person = stack.new_person()
    saves = {
        "saves": [
            {"concert_id": ONE.id, "reason": "First"},
            {"concert_id": TWO.id},
            {"concert_id": "gone-from-the-source"},
        ]
    }
    for _ in range(2):
        imported = await api.post("/account/saved/import", json=saves, headers=bearer(person))
        assert imported.status_code == 200
        assert imported.json()["failed"] == ["gone-from-the-source"]
    assert sorted(await saved_ids(api, person)) == sorted([ONE.id, TWO.id])


async def test_a_concert_the_source_lacks_is_never_saved(api: httpx.AsyncClient) -> None:
    person = stack.new_person()
    response = await api.put("/account/saved/not-a-concert", json={}, headers=bearer(person))
    assert response.status_code == 404
    assert response.json()["code"] == "concert_not_found"
    assert await saved_ids(api, person) == []


async def test_a_catalog_concert_saves_by_its_source_id(
    api: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog_concert = ONE.model_copy(update={"id": "jambase:17324221", "source": "jambase"})

    async def from_catalog(_: object, __: object, concert_id: str) -> Concert:
        if concert_id != catalog_concert.id:
            raise pool.ConcertNotFound
        return catalog_concert

    monkeypatch.setattr(pool, "find_concert", from_catalog)
    person = stack.new_person()
    saved = await api.put(f"/account/saved/{catalog_concert.id}", json={}, headers=bearer(person))
    assert saved.status_code == 200
    assert await saved_ids(api, person) == [catalog_concert.id]


async def test_tokens_this_project_did_not_sign_are_refused(api: httpx.AsyncClient) -> None:
    person = stack.new_person()
    header, claims = (
        json.loads(base64.urlsafe_b64decode(part + "==")) for part in person.token.split(".")[:2]
    )
    for kid in (header["kid"], "another-project"):
        key = ECKey.generate_key("P-256", parameters={"kid": kid})
        forged = jwt.encode({"alg": "ES256", "kid": kid}, claims, key)
        response = await api.get("/account/saved", headers={"Authorization": f"Bearer {forged}"})
        assert response.status_code == 401
    for authorization in ("", "Bearer", "Bearer not-a-token", f"Basic {person.token}"):
        response = await api.get("/account/saved", headers={"Authorization": authorization})
        assert response.status_code == 401
        assert response.json()["code"] == "sign_in"


async def test_deleting_an_account_needs_a_recent_sign_in_and_removes_its_saves(
    api: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    person = stack.new_person()
    await api.put(f"/account/saved/{ONE.id}", json={}, headers=bearer(person))

    later = time.time() + accounts.RECENT_SIGN_IN + 60
    with monkeypatch.context() as clock:
        clock.setattr(accounts.time, "time", lambda: later)
        stale = await api.delete("/account", headers=bearer(person))
    assert stale.status_code == 403
    assert stale.json()["code"] == "sign_in_again"
    assert await saved_ids(api, person) == [ONE.id]

    assert (await api.delete("/account", headers=bearer(person))).status_code == 204
    with pytest.raises(httpx.HTTPStatusError):
        stack.sign_in(person.email)
    async with httpx.AsyncClient(headers={"apikey": stack.secret_key()}) as server:
        rows = await server.get(
            f"{stack.URL}/rest/v1/saved_concerts",
            params={"select": "concert_id", "user_id": f"eq.{person.id}"},
        )
    assert rows.status_code == 200
    assert rows.json() == []


async def test_the_daily_keep_awake_reaches_the_database() -> None:
    async with supabase.make_client(stack.URL) as client:
        await supabase.keep_awake(client, SecretStr(stack.secret_key()))
        with pytest.raises(supabase.SupabaseError):
            await supabase.keep_awake(client, SecretStr("sb_secret_not_this_project"))
