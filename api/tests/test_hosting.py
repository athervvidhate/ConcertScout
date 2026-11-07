"""The public entrypoint refuses unsafe local defaults before serving any request."""

import json
import runpy
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from redis.asyncio import Redis

from concert_scout.config import Settings
from concert_scout.hosting import validate_public_settings

PUBLIC = {
    "tm_key": "unused-test-key",
    "anthropic_api_key": "unused-test-key",
    "geoapify_key": "unused-test-key",
    "redis_url": "rediss://default:private-password@redis.example.com:6379",
    "cors_origins": ["https://concerts.example.com"],
    "turnstile_secret": "private-production-secret",
    "client_ip_header": "x-vercel-forwarded-for",
}


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"redis_url": "redis://default:private-password@redis.example.com:6379"}, "REDIS_URL"),
        ({"redis_url": "rediss://redis.example.com:6379"}, "REDIS_URL"),
        ({"cors_origins": ["http://localhost:3000"]}, "CORS_ORIGINS"),
        ({"cors_origins": ["https://*.example.com"]}, "CORS_ORIGINS"),
        ({"cors_origins": []}, "CORS_ORIGINS"),
        ({"cors_origins": ["https://concerts.example.com/path"]}, "CORS_ORIGINS"),
        ({"turnstile_secret": "1x0000000000000000000000000000000AA"}, "TURNSTILE_SECRET"),
        ({"client_ip_header": None}, "CLIENT_IP_HEADER"),
        ({"spotify_client_id": "configured"}, "SPOTIFY_REDIRECT_URI"),
    ],
)
def test_public_configuration_refuses_unsafe_defaults_without_printing_secrets(
    change: dict[str, Any], field: str
) -> None:
    settings = Settings(_env_file=None, **(PUBLIC | change))  # pyright: ignore[reportCallIssue]
    with pytest.raises(ValueError, match=field) as caught:
        validate_public_settings(settings)
    assert "private-password" not in str(caught.value)
    assert "private-production-secret" not in str(caught.value)


async def test_actual_public_entrypoint_serves_health_without_redis_or_provider_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in PUBLIC.items():
        monkeypatch.setenv(name.upper(), json.dumps(value) if isinstance(value, list) else value)
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "")

    async def no_io(*_: Any, **__: Any) -> Any:
        raise AssertionError("Health must not call Redis or a provider")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", no_io)
    monkeypatch.setattr(Redis, "execute_command", no_io)
    namespace = runpy.run_path(str(Path(__file__).parents[1] / "index.py"))
    app: FastAPI = namespace["app"]
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="https://api.example.com"
        ) as client:
            response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
