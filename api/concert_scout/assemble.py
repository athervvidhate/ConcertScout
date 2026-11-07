"""Step 7: build the Poster. Every fact comes from the source record, never the model."""

import logging
from collections import defaultdict
from collections.abc import Sequence

from concert_scout.matching import NARROW_GENRE_WEIGHT, Candidate, Match
from concert_scout.models import Concert, Recommendation
from concert_scout.names import normalize
from concert_scout.ranker import Pick

logger = logging.getLogger(__name__)

POSTER_SIZE = 8
# The most a genre alone can score, so with no ranker to drop them, genre fillers never qualify.
QUALIFYING_SCORE = NARROW_GENRE_WEIGHT
NOTABLE_REASON = "Coming up nearby"
MAX_STYLES = 3


def _headliner(concert: Concert) -> str:
    return normalize(concert.artists[0].name if concert.artists else concert.name)


def _stacked(
    recommendations: Sequence[Recommendation], shortlist: Sequence[Candidate]
) -> list[Recommendation]:
    """One Recommendation per Artist, carrying their other dates.

    Sources list one Concert more than once under different venue names, so an Artist's date
    only ever counts once.
    """
    by_artist: defaultdict[str, list[Concert]] = defaultdict(list)
    for candidate in shortlist:
        by_artist[_headliner(candidate.concert)].append(candidate.concert)

    stacked: dict[str, Recommendation] = {}
    for recommendation in recommendations:
        artist = _headliner(recommendation.concert)
        if artist in stacked:
            continue
        dates = {recommendation.concert.date: recommendation.concert}
        for concert in by_artist[artist]:
            dates.setdefault(concert.date, concert)
        also = [c for c in dates.values() if c is not recommendation.concert]
        also.sort(key=lambda c: (c.date is None, c.date))
        stacked[artist] = recommendation.model_copy(update={"also": also})
    return list(stacked.values())


def from_picks(picks: Sequence[Pick], shortlist: Sequence[Candidate]) -> list[Recommendation]:
    """The best picks that name a shortlisted Concert, with only the reason kept from the model.

    A seed Artist was asked for by name, so they lead the Poster whatever the model did.
    """
    concerts = {candidate.concert.id: candidate.concert for candidate in shortlist}
    best: dict[str, Pick] = {}
    for pick in sorted(picks, key=lambda p: p.score, reverse=True):
        # The model sometimes pads its answer with an empty row, which is not a recommendation.
        if pick.id in concerts and pick.score >= 50 and pick.reason.strip():
            best.setdefault(pick.id, pick)
    unknown = sum(pick.id not in concerts for pick in picks)
    if unknown:
        logger.warning("Dropped %d picks with unknown IDs", unknown)
    chosen = [
        Recommendation(concert=concerts[p.id], reason=p.reason, score=p.score)
        for p in best.values()
    ]
    seeds = [
        Recommendation(concert=candidate.concert, reason=_neutral_reason(match))
        for candidate in shortlist
        if (match := candidate.match) and match.signal == "seed"
    ]
    seed_artists = {_headliner(seed.concert) for seed in seeds}
    # The sort is stable, so a seed the model picked keeps its reason over the neutral one.
    ordered = sorted([*chosen, *seeds], key=lambda r: _headliner(r.concert) not in seed_artists)
    return _stacked(ordered, shortlist)[:POSTER_SIZE]


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
    return _stacked(recommendations, shortlist)[:POSTER_SIZE]


def from_notable(shortlist: Sequence[Candidate]) -> list[Recommendation]:
    """A Search with no Taste. The shortlist is already notable and soonest first."""
    chosen = [Recommendation(concert=c.concert, reason=NOTABLE_REASON) for c in shortlist]
    return _stacked(chosen, shortlist)[:POSTER_SIZE]


def _neutral_reason(match: Match) -> str:
    if match.signal == "seed":
        return f"{match.artist} is in your Search"
    if match.signal == "one_hop":
        return f"{match.artist} is similar to {match.via}"
    if match.signal == "two_hops":
        return f"{match.artist} is close to Artists similar to {match.via}"
    if match.via:
        return f"{match.artist} shares tags with {match.via}"
    return f"Tagged {_listed(match.styles[:MAX_STYLES])}" if match.styles else NOTABLE_REASON


def _listed(items: Sequence[str]) -> str:
    return ", ".join(items[:-1]) + " and " + items[-1] if len(items) > 1 else items[0]
