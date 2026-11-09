"""The local Supabase stack from `supabase/`, started with `make supabase`.

Its keys come from the running stack, so none sit in the repo. They open nothing outside this
machine.
"""

import json
import os
import secrets
import subprocess
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]


@cache
def secret_key() -> str:
    """Read only when a test needs the stack, so other tests run without it."""
    return os.environ.get("SUPABASE_SECRET_KEY") or _status()["SECRET_KEY"]


def _status() -> dict[str, str]:
    cli = ROOT / "frontend" / "node_modules" / ".bin" / "supabase"
    shown = subprocess.run(
        [cli, "status", "-o", "json", "--workdir", ROOT],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(shown.stdout[shown.stdout.index("{") :])


URL = os.environ.get("SUPABASE_URL", "http://127.0.0.1:54321")
PUBLISHABLE_KEY = os.environ.get(
    "SUPABASE_PUBLISHABLE_KEY", "sb_publishable_ACJWlzQHlZjBrEguHvfOxg_3BJgxAaH"
)
PASSWORD = "correct horse battery staple"


@dataclass(frozen=True)
class Person:
    id: str
    email: str
    token: str


def stack_transport(
    others: httpx.AsyncBaseTransport,
) -> httpx.AsyncBaseTransport:
    """Real HTTP to the local stack only. Every other host goes to `others`."""
    real = httpx.AsyncHTTPTransport()
    host = httpx.URL(URL).host

    class Routed(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            target = real if request.url.host == host else others
            return await target.handle_async_request(request)

    return Routed()


def new_person() -> Person:
    """A confirmed account with a real access token from the stack's password sign-in."""
    email = f"person-{secrets.token_hex(6)}@example.com"
    admin = {"apikey": secret_key()}
    created = httpx.post(
        f"{URL}/auth/v1/admin/users",
        headers=admin,
        json={"email": email, "password": PASSWORD, "email_confirm": True},
    )
    created.raise_for_status()
    return Person(id=created.json()["id"], email=email, token=sign_in(email))


def sign_in(email: str) -> str:
    response = httpx.post(
        f"{URL}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": PUBLISHABLE_KEY},
        json={"email": email, "password": PASSWORD},
    )
    response.raise_for_status()
    return response.json()["access_token"]


def rest(token: str) -> httpx.Client:
    """The Data API as a signed-in browser reaches it, with only the public key."""
    return httpx.Client(
        base_url=f"{URL}/rest/v1",
        headers={"apikey": PUBLISHABLE_KEY, "Authorization": f"Bearer {token}"},
    )
