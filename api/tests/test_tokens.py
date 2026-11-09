"""Access-token checks: expiry, audience, issuer and signing-key rotation.

The project's signing keys are generated here and published as a standard JWK set.
"""

import time
from typing import Any

import httpx
import pytest
from joserfc import jwt
from joserfc.jwk import ECKey, Key, KeySet

from concert_scout.sources import supabase

PROJECT = "https://project.supabase.co"


class Project:
    def __init__(self) -> None:
        self.keys = [ECKey.generate_key("P-256", parameters={"kid": "first"})]
        self.fetches = 0

    def rotate(self) -> None:
        self.keys.append(ECKey.generate_key("P-256", parameters={"kid": "second"}))

    def handle(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/auth/v1/.well-known/jwks.json"
        self.fetches += 1
        return httpx.Response(200, json=KeySet(list[Key](self.keys)).as_dict(private=False))

    def token(self, **overrides: Any) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": f"{PROJECT}/auth/v1",
            "aud": "authenticated",
            "role": "authenticated",
            "sub": "person",
            "exp": now + 3600,
            "iat": now,
            "amr": [{"method": "password", "timestamp": now - 5}],
        } | overrides
        key = self.keys[-1]
        return jwt.encode({"alg": "ES256", "kid": key.kid}, claims, key)


@pytest.fixture
def project() -> Project:
    return Project()


@pytest.fixture
def verifier(project: Project) -> supabase.Verifier:
    client = supabase.make_client(PROJECT, httpx.MockTransport(project.handle))
    return supabase.Verifier(client)


async def test_a_current_token_names_its_account_and_sign_in_time(
    project: Project, verifier: supabase.Verifier
) -> None:
    account = await verifier.verify(project.token())
    assert account.id == "person"
    assert time.time() - account.authenticated_at < 60


async def test_a_token_from_a_clock_a_few_seconds_ahead_is_accepted(
    project: Project, verifier: supabase.Verifier
) -> None:
    """Supabase's clock can run a little ahead of the API's, so a fresh token looks early."""
    account = await verifier.verify(project.token(iat=int(time.time()) + 3))
    assert account.id == "person"


@pytest.mark.parametrize(
    "claims",
    [
        {"exp": int(time.time()) - 60},
        {"iat": int(time.time()) + 120},
        {"aud": "anon"},
        {"role": "anon"},
        {"iss": "https://other.supabase.co/auth/v1"},
        {"is_anonymous": True},
    ],
)
async def test_tokens_that_are_expired_or_meant_for_others_are_refused(
    project: Project, verifier: supabase.Verifier, claims: dict[str, Any]
) -> None:
    with pytest.raises(supabase.InvalidToken):
        await verifier.verify(project.token(**claims))


async def test_a_rotated_signing_key_is_fetched_once_and_then_trusted(
    project: Project, verifier: supabase.Verifier, monkeypatch: pytest.MonkeyPatch
) -> None:
    await verifier.verify(project.token())
    project.rotate()
    monkeypatch.setattr(supabase, "REFETCH_GAP", 0.0)
    await verifier.verify(project.token())
    await verifier.verify(project.token())
    assert project.fetches == 2
