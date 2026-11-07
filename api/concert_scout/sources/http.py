import httpx
from httpx_retries import Retry, RetryTransport

USER_AGENT = "ConcertScout (+https://github.com/athervvidhate/ConcertScoutAI)"


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
