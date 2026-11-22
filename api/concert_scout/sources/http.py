import logging

import httpx
from httpx_retries import Retry, RetryTransport

USER_AGENT = "ConcertScout (+https://github.com/athervvidhate/ConcertScoutAI)"

# httpx logs every request URL at INFO, and several sources take their API key as a query
# parameter, so those logs would carry the keys. Only its warnings and errors are kept.
logging.getLogger("httpx").setLevel(logging.WARNING)


def make_client(
    base_url: str, params: dict[str, str], transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base_url,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=10.0,
        transport=RetryTransport(transport, retry=Retry(total=2, backoff_factor=0.5)),
    )
