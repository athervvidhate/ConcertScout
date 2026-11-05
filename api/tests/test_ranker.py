from concert_scout import assemble
from concert_scout.matching import Candidate, Match, Signal
from concert_scout.models import Artist, Concert
from concert_scout.ranker import Pick


def candidate(id: str, score: float, signal: Signal) -> Candidate:
    return Candidate(
        concert=Concert(
            id=id,
            name="Source event",
            url="https://tickets.example",
            artists=[Artist(name="Source Artist")],
        ),
        match=Match(artist="Source Artist", signal=signal, score=score, via="Khruangbin"),
    )


def test_unknown_ids_are_dropped_and_facts_come_from_source() -> None:
    source = candidate("known", 1, "seed")
    result = assemble.from_picks(
        [
            Pick(id="unknown", score=100, reason="fake"),
            Pick(id="known", score=81, reason="Similar sound"),
        ],
        [source],
    )
    assert len(result) == 1
    assert result[0].concert == source.concert
    assert result[0].reason == "Similar sound"


def test_fallback_drops_genre_filler_and_unmatched() -> None:
    rows = [
        candidate("seed", 1, "seed"),
        candidate("near", 0.64, "one_hop"),
        candidate("weak", 0.15, "genre"),
    ]
    assert [r.concert.id for r in assemble.from_matches(rows)] == ["seed", "near"]
