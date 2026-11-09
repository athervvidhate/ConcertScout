"""Measures over a judged Poster and its source Concert records."""

from collections.abc import Sequence
from dataclasses import dataclass

from concert_scout.models import Concert, Recommendation
from concert_scout.names import normalize


@dataclass(frozen=True)
class Measures:
    bad_artists: int
    must_found: int
    must_total: int
    judged_good_recommendations: int
    recommendations: int
    invented_or_unknown: int


def measure(
    poster: Sequence[Recommendation],
    source: Sequence[Concert],
    must: Sequence[str],
    good: Sequence[str],
    bad: Sequence[str],
) -> Measures:
    """Count each named Artist once; count Poster quality by Recommendation."""
    must_names = {normalize(name) for name in must}
    good_names = {normalize(name) for name in good} | must_names
    bad_names = {normalize(name) for name in bad}
    source_by_id = {concert.id: concert for concert in source}
    seen: set[str] = set()
    good_count = 0
    invented = 0
    for recommendation in poster:
        concert = recommendation.concert
        names = {normalize(artist.name) for artist in concert.artists}
        seen.update(names)
        good_count += bool(names & good_names)
        invented += source_by_id.get(concert.id) != concert
    return Measures(
        bad_artists=len(seen & bad_names),
        must_found=len(seen & must_names),
        must_total=len(must_names),
        judged_good_recommendations=good_count,
        recommendations=len(poster),
        invented_or_unknown=invented,
    )
