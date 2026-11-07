import datetime as dt

from concert_scout import assemble, ranker
from concert_scout.interpreter import Interpretation
from concert_scout.matching import Candidate, Match, Signal
from concert_scout.models import Artist, Concert
from concert_scout.ranker import Fit


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
    result = assemble.from_fits(
        [
            Fit(id="unknown", level=3, reason="fake"),
            Fit(id="known", level=3, reason="Similar sound"),
        ],
        [source],
    )
    assert len(result) == 1
    assert result[0].concert == source.concert
    assert result[0].reason == "Similar sound"


def test_a_seed_the_model_left_out_still_leads_the_poster() -> None:
    seed = candidate("seed", 1, "seed", artist="Niall Horan")
    similar = candidate("similar", 0.8, "one_hop", artist="Harry Styles")
    poster = assemble.from_fits(
        [Fit(id="similar", level=3, reason="Soft pop rock")], [seed, similar]
    )
    assert [r.concert.id for r in poster] == ["seed", "similar"]
    assert poster[0].reason == "Niall Horan is in your Search"
    assert poster[0].score is None


def test_a_seed_the_model_picked_leads_and_keeps_its_reason() -> None:
    seed = candidate("seed", 1, "seed", artist="Niall Horan")
    similar = candidate("similar", 0.8, "one_hop", artist="Harry Styles")
    picks = [
        Fit(id="similar", level=3, reason="Soft pop rock"),
        Fit(id="seed", level=2, reason="Irish singer-songwriter with bright pop hooks"),
    ]
    poster = assemble.from_fits(picks, [seed, similar])
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
                    '{"fits":[{"id":"fake","level":3,"reason":"fake"},'
                    '{"id":"known","level":3,"reason":"A close match"}]}'
                )
            ]
        )

    source = candidate("known", 1, "seed")
    interpretation = Interpretation(
        artists=["Khruangbin"], descriptors=[], tags=[], place=None, start=None, end=None
    )
    fits = await rank(interpretation, [source], {}, FunctionModel(respond))
    result = assemble.from_fits(fits, [source])
    assert len(result) == 1
    assert result[0].concert == source.concert
    assert result[0].reason == "A close match"


def test_a_padded_empty_row_is_not_a_recommendation() -> None:
    rows = [candidate("real", 1, "seed"), candidate("pad", 0.8, "one_hop")]
    picks = [Fit(id="real", level=3, reason="Close match"), Fit(id="pad", level=3, reason=" ")]
    assert [r.concert.id for r in assemble.from_fits(picks, rows)] == ["real"]


def test_an_artist_stacks_their_dates_and_one_date_counts_once() -> None:
    first, second = dt.date(2027, 3, 6), dt.date(2027, 3, 7)
    rows = [
        candidate("belly-up", 1, "seed", "49 Winchester", first),
        candidate("belly-up-tavern", 1, "seed", "49 winchester", first),
        candidate("next-night", 1, "seed", "49 Winchester", second),
        candidate("other", 1, "seed", "Wade Bowen", first),
    ]
    picks = [Fit(id=c.concert.id, level=3, reason="Fits") for c in rows]
    poster = assemble.from_fits(picks, rows)
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


def test_votes_take_the_median_level_and_the_most_favourable_reason() -> None:
    votes = [
        [Fit(id="a", level=3, reason="Dusty psych-funk"), Fit(id="b", level=1)],
        [Fit(id="a", level=2, reason="Groovy"), Fit(id="b", level=2, reason="Close-ish")],
        [Fit(id="a", level=0), Fit(id="b", level=1)],
    ]
    tallied = {fit.id: fit for fit in ranker.tally(votes)}
    assert tallied["a"] == Fit(id="a", level=2, reason="Dusty psych-funk")
    assert tallied["b"].level == 1


def test_a_vote_that_skipped_a_concert_does_not_count_against_it() -> None:
    votes = [[Fit(id="a", level=3, reason="Fits")], [], [Fit(id="a", level=3, reason="Fits")]]
    assert ranker.tally(votes) == [Fit(id="a", level=3, reason="Fits")]


def test_ties_go_to_the_stronger_match() -> None:
    weak = candidate("weak", 0.3, "tags")
    strong = candidate("strong", 0.8, "one_hop")
    fits = [Fit(id="weak", level=3, reason="Fits"), Fit(id="strong", level=3, reason="Fits")]
    assert [r.concert.id for r in assemble.from_fits(fits, [weak, strong])] == ["strong", "weak"]


def test_a_stretch_stays_off_the_poster() -> None:
    rows = [candidate("fair", 0.5, "tags"), candidate("stretch", 0.5, "genre")]
    fits = [Fit(id="fair", level=2, reason="Close"), Fit(id="stretch", level=1, reason="Loose")]
    assert [r.concert.id for r in assemble.from_fits(fits, rows)] == ["fair"]


def test_later_votes_see_the_rows_in_another_fixed_order() -> None:
    rows = [candidate(str(n), 1 - n / 10, "one_hop") for n in range(6)]
    empty = Interpretation(artists=[], descriptors=[], tags=[], place=None, start=None, end=None)
    first, second = (ranker.build_prompt(empty, rows, {}, vote) for vote in (0, 1))
    assert first != second
    assert second == ranker.build_prompt(empty, rows, {}, 1)
    assert sorted(first) == sorted(second)


async def test_a_failed_vote_drops_out_and_the_others_count() -> None:
    from collections.abc import Sequence

    from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
    from pydantic_ai.models.function import AgentInfo, FunctionModel

    calls: list[int] = []

    def respond(_: Sequence[ModelMessage], __: AgentInfo) -> ModelResponse:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("one vote fails")
        return ModelResponse(parts=[TextPart('{"fits":[{"id":"x","level":3,"reason":"Fits"}]}')])

    source = candidate("x", 1, "one_hop")
    empty = Interpretation(artists=[], descriptors=[], tags=[], place=None, start=None, end=None)
    fits = await ranker.rank(empty, [source], {}, FunctionModel(respond))
    assert fits == [Fit(id="x", level=3, reason="Fits")]
