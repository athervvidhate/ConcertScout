"""Step 7: build the Poster. Every fact comes from the source record, never the model."""

import datetime as dt
import logging
from collections import defaultdict
from collections.abc import Mapping, Sequence

from concert_scout.matching import NARROW_GENRE_WEIGHT, Candidate, Match
from concert_scout.models import Concert, Recommendation
from concert_scout.names import normalize

logger = logging.getLogger(__name__)

POSTER_SIZE = 8
# A fair suggestion or better. See jev.LEVELS.
MIN_LEVEL = 2
# The most a genre alone can score, so with no ranker to drop them, genre fillers never qualify.
QUALIFYING_SCORE = NARROW_GENRE_WEIGHT
NOTABLE_REASON = "Coming up nearby"
MAX_STYLES = 3


def upcoming(recommendations: Sequence[Recommendation], today: dt.date) -> list[Recommendation]:
    """Drop Concerts that have passed, from a stored Poster that is read later."""
    kept: list[Recommendation] = []
    for pick in recommendations:
        if pick.concert.date and pick.concert.date < today:
            continue
        also = [c for c in pick.also if not c.date or c.date >= today]
        kept.append(pick.model_copy(update={"also": also}))
    return kept


def _headliner(concert: Concert) -> str:
    """The key that stacks one Artist's dates. A Concert with no Lineup stands alone."""
    return normalize(concert.artists[0].name) if concert.artists else f"concert:{concert.id}"


def _stacked(
    recommendations: Sequence[Recommendation], shortlist: Sequence[Candidate]
) -> list[Recommendation]:
    """One Recommendation per Artist, carrying their other dates.

    Keep separate venues and known performance times on the same day. Cross-source duplicates
    have already been reconciled by the pool.
    """
    by_artist: defaultdict[str, list[Concert]] = defaultdict(list)
    for candidate in shortlist:
        by_artist[_headliner(candidate.concert)].append(candidate.concert)

    stacked: dict[str, Recommendation] = {}
    for recommendation in recommendations:
        artist = _headliner(recommendation.concert)
        if artist in stacked:
            continue

        def identity(c: Concert) -> tuple[object, ...]:
            return c.date, normalize(c.venue or ""), normalize(c.city or ""), c.time

        dates = {identity(recommendation.concert): recommendation.concert}
        for concert in by_artist[artist]:
            dates.setdefault(identity(concert), concert)
        also = [c for c in dates.values() if c is not recommendation.concert]
        also.sort(key=lambda c: (c.date is None, c.date))
        stacked[artist] = recommendation.model_copy(update={"also": also})
    return list(stacked.values())


def from_levels(levels: Mapping[str, int], shortlist: Sequence[Candidate]) -> list[Recommendation]:
    """The best-graded Concerts in the shortlist, each with a neutral reason for now.

    Ties go to the stronger match and then to shortlist order, so the grade is the only thing
    that can move a Concert. A seed Artist was asked for by name, so they lead the Poster
    whatever their grade.
    """
    position = {candidate.concert.id: n for n, candidate in enumerate(shortlist)}
    concerts = {candidate.concert.id: candidate for candidate in shortlist}
    unknown = sum(id_ not in concerts for id_ in levels)
    if unknown:
        logger.warning("Dropped %d grades with unknown IDs", unknown)
    good = [id_ for id_, level in levels.items() if id_ in concerts and level >= MIN_LEVEL]

    def order(id_: str) -> tuple[int, float, int]:
        match = concerts[id_].match
        return (-levels[id_], -(match.score if match else 0), position[id_])

    chosen = [
        Recommendation(
            concert=concerts[id_].concert,
            reason=_reason(concerts[id_]),
            score=levels[id_],
        )
        for id_ in sorted(good, key=order)
    ]
    seeds = [
        Recommendation(concert=candidate.concert, reason=_neutral_reason(match))
        for candidate in shortlist
        if (match := candidate.match) and match.signal == "seed"
    ]
    seed_artists = {_headliner(seed.concert) for seed in seeds}
    # The sort is stable, so a graded seed keeps its level over the ungraded copy.
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


def _reason(candidate: Candidate) -> str:
    return _neutral_reason(candidate.match) if candidate.match else NOTABLE_REASON


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
