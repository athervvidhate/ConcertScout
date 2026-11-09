import httpx

from concert_scout.sources import http

BASE_URL = "https://api.resend.com"
# Resend's shared sender, which reaches the account's own address with no domain to verify.
SENDER = "Concert Scout <onboarding@resend.dev>"
# Alerts go to people, so they come from the verified domain (ADR 0006).
ALERT_SENDER = "Concert Scout <alerts@concertscout.app>"


class ResendError(Exception):
    """The email did not go out. The message never holds the API key or the report."""


def make_client(
    api_key: str, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    client = http.make_client(BASE_URL, {}, transport)
    client.headers["Authorization"] = f"Bearer {api_key}"
    return client


async def send(
    client: httpx.AsyncClient,
    to: str,
    subject: str,
    text: str,
    *,
    sender: str = SENDER,
    headers: dict[str, str] | None = None,
    idempotency_key: str | None = None,
) -> None:
    """`idempotency_key` makes Resend accept a repeated send without sending it twice."""
    body: dict[str, object] = {"from": sender, "to": [to], "subject": subject, "text": text}
    if headers:
        body["headers"] = headers
    request_headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
    try:
        response = await client.post("/emails", json=body, headers=request_headers)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ResendError(f"status {exc.response.status_code}") from None
    except httpx.HTTPError as exc:
        raise ResendError(type(exc).__name__) from None
