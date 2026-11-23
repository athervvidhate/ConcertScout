import logging

import httpx
from httpx_retries import Retry, RetryTransport

USER_AGENT = "ConcertScout (+https://github.com/athervvidhate/ConcertScoutAI)"

# httpx logs every request URL at INFO, and several sources take their API key as a query
# parameter, so those logs would carry the keys. Only its warnings and errors are kept.
logging.getLogger("httpx").setLevel(logging.WARNING)


def make_client(
    base_url: str,
    params: dict[str, str],
    transport: httpx.AsyncBaseTransport | None = None,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
    retries: int = 2,
) -> httpx.AsyncClient:
    effective_headers = {"User-Agent": USER_AGENT, **(headers or {})}
    effective_transport: httpx.AsyncBaseTransport | None = (
        RetryTransport(transport, retry=Retry(total=retries, backoff_factor=0.5))
        if retries > 0
        else transport
    )
    return httpx.AsyncClient(
        base_url=base_url,
        params=params,
        headers=effective_headers,
        timeout=timeout,
        transport=effective_transport,
    )
