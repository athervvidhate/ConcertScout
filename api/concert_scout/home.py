"""Public example Posters. Only the authenticated nightly job can build them."""

import datetime as dt
import logging

from pydantic import BaseModel
from redis.asyncio import Redis

from concert_scout import cache, limits
from concert_scout.models import Candidates, Interpreted, Poster, Recommendation
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
        picks: list[Recommendation] = []
        for pick in example.poster.recommendations:
            if pick.concert.date and pick.concert.date < today:
                continue
            also = [c for c in pick.also if not c.date or c.date >= today]
            picks.append(pick.model_copy(update={"also": also}))
        visible.append(example.model_copy(update={"poster": Poster(recommendations=picks)}))
    return Examples(examples=visible)


async def refresh(services: Services) -> None:
    examples: list[Example] = []
    for text in EXAMPLES:
        try:
            await limits.check_spend(services.redis)
        except limits.SpendCapReached:
            break
        interpreted = None
        candidates = None
        poster = None
        failed = False
        async for event in run_search(text, [], None, "UTC", services):
            if event.event == "interpreted":
                interpreted = Interpreted.model_validate(
                    {field: event.data.get(field) for field in Interpreted.model_fields}
                )
            elif event.event == "candidates":
                candidates = Candidates.model_validate(event.data)
            elif event.event == "poster":
                poster = Poster.model_validate(event.data)
            elif event.event == "error":
                failed = True
        if poster is not None and not failed:
            examples.append(
                Example(text=text, interpreted=interpreted, candidates=candidates, poster=poster)
            )
    # A failed refresh must not replace a good cache with an empty one.
    if examples:
        await cache.write(services.redis, KEY, Examples(examples=examples), TTL)
