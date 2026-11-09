"""Public example Posters. Only the authenticated nightly job can build them."""

import datetime as dt
import logging

from pydantic import BaseModel
from redis.asyncio import Redis

from concert_scout import assemble, cache, limits
from concert_scout.models import Candidates, Interpreted, Poster
from concert_scout.pipeline import Services, run_search

logger = logging.getLogger(__name__)
EXAMPLES = (
    "Tame Impala in London next summer",
    "Jazz in New Orleans this weekend",
    "Dreamy bands in SoCal next month",
)
KEY = "home:examples:v1"
TTL = dt.timedelta(hours=30)


class Example(BaseModel):
    text: str
    interpreted: Interpreted | None = None
    candidates: Candidates | None = None
    poster: Poster


class Examples(BaseModel):
    examples: list[Example] = []


async def read(redis: Redis, today: dt.date) -> Examples:
    """A missing cache stays empty. This read cannot call any provider or model."""
    stored = await cache.read(redis, KEY, Examples)
    if stored is None:
        return Examples()
    visible: list[Example] = []
    for example in stored.examples:
        if example.interpreted and example.interpreted.end and example.interpreted.end < today:
            continue
        picks = assemble.upcoming(example.poster.recommendations, today)
        visible.append(example.model_copy(update={"poster": Poster(recommendations=picks)}))
    return Examples(examples=visible)


async def refresh(services: Services) -> None:
    """Saves each Example as it lands, so a run cut off by the time limit keeps what it built.

    An Example that fails keeps its last good Poster until the cache expires.
    """
    stored = await cache.read(services.redis, KEY, Examples)
    built = {example.text: example for example in stored.examples} if stored else {}
    for text in EXAMPLES:
        try:
            await limits.check_spend(services.redis)
        except limits.SpendCapReached:
            break
        example = await _build(text, services)
        if example is None:
            continue
        built[text] = example
        ordered = [built[t] for t in EXAMPLES if t in built]
        await cache.write(services.redis, KEY, Examples(examples=ordered), TTL)


async def _build(text: str, services: Services) -> Example | None:
    interpreted = None
    candidates = None
    poster = None
    async for event in run_search(text, [], None, "UTC", services):
        if event.event == "interpreted":
            interpreted = Interpreted.model_validate(event.data)
        elif event.event == "candidates":
            candidates = Candidates.model_validate(event.data)
        elif event.event == "poster":
            poster = Poster.model_validate(event.data)
        elif event.event == "error":
            logger.warning("Example %r failed: %s", text, event.data.get("code"))
            return None
    if poster is None:
        return None
    return Example(text=text, interpreted=interpreted, candidates=candidates, poster=poster)
