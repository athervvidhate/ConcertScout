"""Keeps the API safe to expose, because the browser calls it directly (ADR 0001)."""

import logging

import httpx
from fastapi import Request
from pydantic import SecretStr
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from concert_scout.models import SearchError
from concert_scout.sources import http

logger = logging.getLogger(__name__)

TURNSTILE_URL = "https://challenges.cloudflare.com/turnstile/v0"
HEADERS = [
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
]


class Refused(Exception):
    """A request stopped before it could spend anything."""

    def __init__(
        self, status: int, code: str, message: str, retry_after: int | None = None
    ) -> None:
        super().__init__(code)
        self.status = status
        self.error = SearchError(code=code, message=message, retry_after=retry_after)


def client_ip(request: Request, trusted_header: str | None) -> str:
    """Anyone can send a forwarding header, so only one the host sets is read.

    The host appends the address it saw, so the last entry is the one a visitor cannot write.
    """
    if trusted_header and (forwarded := request.headers.get(trusted_header)):
        return forwarded.rsplit(",", 1)[-1].strip()
    return request.client.host if request.client else "unknown"


def make_turnstile_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    return http.make_client(TURNSTILE_URL, {}, transport)


async def verify_turnstile(
    client: httpx.AsyncClient, secret: SecretStr, token: str, ip: str
) -> None:
    form = {"secret": secret.get_secret_value(), "response": token, "remoteip": ip}
    try:
        response = await client.post("/siteverify", data=form)
        response.raise_for_status()
        passed = response.json()["success"] is True
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        logger.warning("Turnstile failed: %s", type(exc).__name__)
        message = "We could not run the bot check. Try again in a minute."
        raise Refused(503, "bot_check_unavailable", message) from None
    if not passed:
        raise Refused(403, "bot_check_failed", "The bot check did not pass. Try again.")


class SecurityHeaders:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [*message["headers"], *HEADERS]
            await send(message)

        await self.app(scope, receive, with_headers)
