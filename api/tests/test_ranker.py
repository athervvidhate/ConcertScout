import datetime as dt

from concert_scout import assemble, ranker
from concert_scout.interpreter import Interpretation
from concert_scout.matching import Candidate, Match, Signal
from concert_scout.models import Artist, Concert
from concert_scout.ranker import Pick


def candidate(
    id: str, score: float, signal: Signal, artist: str | None = None, date: dt.date | None = None
) -> Candidate:
    name = artist or f"Artist {id}"
    return Candidate(
        concert=Concert(
            id=id,
            name="Source event",
            url="https://tickets.example",
            artists=[Artist(name=name)],
            date=date,
        ),
        match=Match(artist=name, signal=signal, score=score, via="Khruangbin"),
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


def test_a_seed_the_model_left_out_still_leads_the_poster() -> None:
    seed = candidate("seed", 1, "seed", artist="Niall Horan")
    similar = candidate("similar", 0.8, "one_hop", artist="Harry Styles")
    poster = assemble.from_picks(
        [Pick(id="similar", score=88, reason="Soft pop rock")], [seed, similar]
    )
    assert [r.concert.id for r in poster] == ["seed", "similar"]
    assert poster[0].reason == "Niall Horan is in your Search"
    assert poster[0].score is None


def test_a_seed_the_model_picked_leads_and_keeps_its_reason() -> None:
    seed = candidate("seed", 1, "seed", artist="Niall Horan")
    similar = candidate("similar", 0.8, "one_hop", artist="Harry Styles")
    picks = [
        Pick(id="similar", score=88, reason="Soft pop rock"),
        Pick(id="seed", score=70, reason="Irish singer-songwriter with bright pop hooks"),
    ]
    poster = assemble.from_picks(picks, [seed, similar])
    assert [r.concert.id for r in poster] == ["seed", "similar"]
    assert poster[0].reason == "Irish singer-songwriter with bright pop hooks"


def test_fallback_drops_genre_filler_and_unmatched() -> None:
    rows = [
        candidate("seed", 1, "seed"),
        candidate("near", 0.64, "one_hop"),
        candidate("weak", 0.15, "genre"),
    ]
    assert [r.concert.id for r in assemble.from_matches(rows)] == ["seed", "near"]


async def test_model_output_is_assembled_from_source() -> None:
    from collections.abc import Sequence

    from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
    from pydantic_ai.models.function import AgentInfo, FunctionModel

    from concert_scout.interpreter import Interpretation
    from concert_scout.ranker import rank

    def respond(_: Sequence[ModelMessage], __: AgentInfo) -> ModelResponse:
        return ModelResponse(
            parts=[
                TextPart(
                    '{"picks":[{"id":"fake","score":100,"reason":"fake"},'
                    '{"id":"known","score":80,"reason":"A close match"}]}'
                )
            ]
        )

    source = candidate("known", 1, "seed")
    interpretation = Interpretation(
        artists=["Khruangbin"], descriptors=[], tags=[], place=None, start=None, end=None
    )
    picks = await rank(interpretation, [source], {}, FunctionModel(respond))
    result = assemble.from_picks(picks, [source])
    assert len(result) == 1
    assert result[0].concert == source.concert
    assert result[0].reason == "A close match"


def test_a_padded_empty_row_is_not_a_recommendation() -> None:
    rows = [candidate("real", 1, "seed"), candidate("pad", 0.8, "one_hop")]
    picks = [Pick(id="real", score=80, reason="Close match"), Pick(id="pad", score=80, reason=" ")]
    assert [r.concert.id for r in assemble.from_picks(picks, rows)] == ["real"]


def test_an_artist_stacks_their_dates_and_one_date_counts_once() -> None:
    first, second = dt.date(2027, 3, 6), dt.date(2027, 3, 7)
    rows = [
        candidate("belly-up", 1, "seed", "49 Winchester", first),
        candidate("belly-up-tavern", 1, "seed", "49 winchester", first),
        candidate("next-night", 1, "seed", "49 Winchester", second),
        candidate("other", 1, "seed", "Wade Bowen", first),
    ]
    picks = [Pick(id=c.concert.id, score=80, reason="Fits") for c in rows]
    poster = assemble.from_picks(picks, rows)
    assert [r.concert.id for r in poster] == ["belly-up", "other"]
    assert [c.id for c in poster[0].also] == ["next-night"]
    assert poster[1].also == []


def test_fallback_reason_names_the_shared_styles() -> None:
    match = Match(
        artist="Son Volt", signal="tags", score=1, styles=["alt-country", "americana", "country"]
    )
    row = Candidate(concert=candidate("x", 1, "tags").concert, match=match)
    assert assemble.from_matches([row])[0].reason == "Tagged alt-country, americana and country"


def test_ranker_sees_each_artist_once() -> None:
    rows = [
        candidate("first", 1, "seed", "49 Winchester"),
        candidate("second", 1, "seed", "49 Winchester"),
    ]
    empty = Interpretation(artists=[], descriptors=[], tags=[], place=None, start=None, end=None)
    assert ranker.build_prompt(empty, rows, {}).count("49 Winchester") == 1
