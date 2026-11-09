"""E2E-only composition: production API/pipeline, real isolated Redis, the local Supabase stack
and domain adapter fixtures.

No production flag enables this. Never import this module from the application package.
"""

import socket
import subprocess
import tempfile
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from pydantic import SecretStr

from concert_scout.app import create_app
from concert_scout.sources import resend
from concert_scout.sources.spotify import Client, Credentials, SpotifyArtist, not_allowed
from tests import supabase_stack
from tests.contracts import contract_model, forbidden_http, install_sources, settings_with

patch = pytest.MonkeyPatch()
install_sources(patch)

with socket.socket() as address:
    address.bind(("127.0.0.1", 0))
    redis_port = address.getsockname()[1]

storage = tempfile.TemporaryDirectory(prefix="concert-scout-e2e-")
redis = subprocess.Popen(
    [
        "redis-server",
        "--bind",
        "127.0.0.1",
        "--port",
        str(redis_port),
        "--save",
        "",
        "--appendonly",
        "no",
        "--dir",
        storage.name,
    ],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
for attempt in range(100):
    try:
        with socket.create_connection(("127.0.0.1", redis_port), timeout=0.1):
            break
    except OSError:
        if redis.poll() is not None or attempt == 99:
            redis.terminate()
            raise RuntimeError("Isolated E2E Redis failed to start") from None
        time.sleep(0.05)


async def exchange(code: str) -> Credentials:
    value = "denied" if code == "not-allowed" else "private-platform-access"
    return Credentials(
        access_token=SecretStr(value),
        refresh_token=SecretStr("private-platform-refresh"),
        expires_at=time.time() + 3600,
    )


async def artists(token: Credentials) -> list[SpotifyArtist]:
    if token.access_token.get_secret_value() == "denied":
        raise not_allowed()
    return [
        SpotifyArtist(
            name="Contract Artist", url="https://open.spotify.com/artist/contract", source="top"
        )
    ]


async def check(token: Credentials) -> None:
    await artists(token)


patch.setattr(Client, "exchange", AsyncMock(side_effect=exchange))
patch.setattr(Client, "artists", AsyncMock(side_effect=artists))
patch.setattr(Client, "check", AsyncMock(side_effect=check))
patch.setattr(resend, "send", AsyncMock())

app = create_app(
    settings_with(
        redis_url=f"redis://127.0.0.1:{redis_port}/0",
        searches_per_hour=1000,
        resend_api_key=SecretStr("test-resend"),
        feedback_email="owner@example.com",
        spotify_client_id="test-client",
        spotify_client_secret=SecretStr("test-secret"),
        spotify_encryption_key=SecretStr(Fernet.generate_key().decode()),
        spotify_redirect_uri="http://127.0.0.1:8146/auth/spotify/callback",
        supabase_url=supabase_stack.URL,
        supabase_publishable_key=supabase_stack.PUBLISHABLE_KEY,
        supabase_secret_key=SecretStr(supabase_stack.secret_key()),
    ),
    # Accounts use the real local Supabase stack; every vendor stays forbidden.
    supabase_stack.stack_transport(httpx.MockTransport(forbidden_http)),
    model=contract_model(),
)
original_lifespan = app.router.lifespan_context


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
    try:
        async with original_lifespan(application):
            yield
    finally:
        redis.terminate()
        redis.wait(timeout=5)
        storage.cleanup()
        patch.undo()


app.router.lifespan_context = lifespan
