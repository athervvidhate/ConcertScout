"""Step 7: build the Poster. Every fact comes from the source record, never the model."""

import logging
from collections.abc import Sequence

from concert_scout.matching import NARROW_GENRE_WEIGHT, Candidate, Match
from concert_scout.models import Recommendation
from concert_scout.ranker import Pick

logger = logging.getLogger(__name__)

POSTER_SIZE = 8
# The most a genre alone can score, so with no ranker to drop them, genre fillers never qualify.
QUALIFYING_SCORE = NARROW_GENRE_WEIGHT
NOTABLE_REASON = "Coming up nearby"


def from_picks(picks: Sequence[Pick], shortlist: Sequence[Candidate]) -> list[Recommendation]:
    """The best picks that name a shortlisted Concert, with only the reason kept from the model."""
    concerts = {candidate.concert.id: candidate.concert for candidate in shortlist}
    best: dict[str, Pick] = {}
    for pick in sorted(picks, key=lambda p: p.score, reverse=True):
        if pick.id in concerts:
            best.setdefault(pick.id, pick)
    unknown = sum(pick.id not in concerts for pick in picks)
    if unknown:
        logger.warning("Dropped %d picks with unknown IDs", unknown)
    chosen = list(best.values())[:POSTER_SIZE]
    return [Recommendation(concert=concerts[p.id], reason=p.reason) for p in chosen]


def from_matches(shortlist: Sequence[Candidate]) -> list[Recommendation]:
    """The fallback when the ranker fails: strong matches only, in shortlist order.

    A Concert with no match has nothing true to say, and a weak one is what the ranker would have
    dropped, so the Poster comes up short rather than padded.
    """
    recommendations = [
        Recommendation(concert=candidate.concert, reason=_neutral_reason(match))
        for candidate in shortlist
        if (match := candidate.match) and match.score > QUALIFYING_SCORE
    ]
    return recommendations[:POSTER_SIZE]


def from_notable(shortlist: Sequence[Candidate]) -> list[Recommendation]:
    """A Search with no Taste. The shortlist is already notable and soonest first."""
    chosen = shortlist[:POSTER_SIZE]
    return [Recommendation(concert=c.concert, reason=NOTABLE_REASON) for c in chosen]


def _neutral_reason(match: Match) -> str:
    if match.signal == "seed":
        return f"{match.artist} is in your Search"
    if match.signal == "one_hop":
        return f"{match.artist} is similar to {match.via}"
    if match.signal == "two_hops":
        return f"{match.artist} is close to Artists similar to {match.via}"
    if match.via:
        return f"{match.artist} shares tags with {match.via}"
    return f"{match.artist} fits the styles in your Search"
