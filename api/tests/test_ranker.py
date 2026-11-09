import datetime as dt
import json
from collections.abc import Sequence
from decimal import Decimal
from typing import cast

import httpx
import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from concert_scout import assemble, ranker, telemetry
from concert_scout.interpreter import Interpretation
from concert_scout.matching import Candidate, Match, Signal
from concert_scout.models import Artist, Concert
from concert_scout.sources import jev

EMPTY = Interpretation(artists=[], descriptors=[], tags=[], place=None, start=None, end=None)


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
    source = candidate("known", 1, "one_hop")
    result = assemble.from_levels({"unknown": 3, "known": 3}, [source])
    assert len(result) == 1
    assert result[0].concert == source.concert
    assert result[0].reason == "Artist known is similar to Khruangbin"
    assert result[0].score == 3


def test_a_seed_graded_low_still_leads_the_poster() -> None:
    seed = candidate("seed", 1, "seed", artist="Niall Horan")
    similar = candidate("similar", 0.8, "one_hop", artist="Harry Styles")
    poster = assemble.from_levels({"similar": 3, "seed": 0}, [seed, similar])
    assert [r.concert.id for r in poster] == ["seed", "similar"]
    assert poster[0].reason == "Niall Horan is in your Search"
    assert poster[0].score is None


def test_a_graded_seed_keeps_its_level() -> None:
    seed = candidate("seed", 1, "seed", artist="Niall Horan")
    similar = candidate("similar", 0.8, "one_hop", artist="Harry Styles")
    poster = assemble.from_levels({"similar": 3, "seed": 2}, [seed, similar])
    assert [(r.concert.id, r.score) for r in poster] == [("seed", 2), ("similar", 3)]


def test_fallback_drops_genre_filler_and_unmatched() -> None:
    rows = [
        candidate("seed", 1, "seed"),
        candidate("near", 0.64, "one_hop"),
        candidate("weak", 0.15, "genre"),
    ]
    assert [r.concert.id for r in assemble.from_matches(rows)] == ["seed", "near"]


def test_an_artist_stacks_their_dates_and_one_date_counts_once() -> None:
    first, second = dt.date(2027, 3, 6), dt.date(2027, 3, 7)
    rows = [
        candidate("belly-up", 1, "seed", "49 Winchester", first),
        candidate("belly-up-tavern", 1, "seed", "49 winchester", first),
        candidate("next-night", 1, "seed", "49 Winchester", second),
        candidate("other", 1, "seed", "Wade Bowen", first),
    ]
    poster = assemble.from_levels({c.concert.id: 3 for c in rows}, rows)
    assert [r.concert.id for r in poster] == ["belly-up", "other"]
    assert [c.id for c in poster[0].also] == ["next-night"]
    assert poster[1].also == []


def test_fallback_reason_names_the_shared_styles() -> None:
    match = Match(
        artist="Son Volt", signal="tags", score=1, styles=["alt-country", "americana", "country"]
    )
    row = Candidate(concert=candidate("x", 1, "tags").concert, match=match)
    assert assemble.from_matches([row])[0].reason == "Tagged alt-country, americana and country"


def test_ties_go_to_the_stronger_match() -> None:
    weak = candidate("weak", 0.3, "tags")
    strong = candidate("strong", 0.8, "one_hop")
    poster = assemble.from_levels({"weak": 3, "strong": 3}, [weak, strong])
    assert [r.concert.id for r in poster] == ["strong", "weak"]


def test_a_stretch_stays_off_the_poster() -> None:
    rows = [candidate("fair", 0.5, "tags"), candidate("stretch", 0.5, "genre")]
    assert [r.concert.id for r in assemble.from_levels({"fair": 2, "stretch": 1}, rows)] == ["fair"]


def test_each_artist_is_graded_once_under_their_first_date() -> None:
    rows = [
        candidate("tm-long-id-1", 1, "seed", "49 Winchester"),
        candidate("tm-long-id-2", 1, "seed", "49 Winchester"),
        candidate("tm-long-id-3", 0.8, "one_hop", "Wade Bowen"),
    ]
    graded = ranker.rows(rows, {})
    assert list(graded) == ["tm-long-id-1", "tm-long-id-3"]
    assert graded["tm-long-id-3"].via == "Khruangbin"


def jev_answer(probabilities: dict[str, dict[str, float]], tokens: int = 1000) -> httpx.Response:
    answers = {name: {"score": 0, "probabilities": p} for name, p in probabilities.items()}
    return httpx.Response(200, json={"answers": answers, "usage": {"input_tokens": tokens}})


async def test_jev_grades_by_the_most_likely_level_and_its_cost_counts() -> None:
    sent: list[dict[str, object]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return jev_answer(
            {
                "strong": {"0": 0.05, "1": 0.05, "2": 0.3, "3": 0.6},
                "tied": {"0": 0.0, "1": 0.5, "2": 0.5, "3": 0.0},
                "partial": {"0": 0.9},
            }
        )

    client = jev.make_client("key", httpx.MockTransport(handle))
    rows = {"strong": '{"artist":"A"}', "tied": '{"artist":"B"}', "partial": '{"artist":"C"}'}
    with telemetry.search() as usage:
        levels = await jev.grade(client, {"artists": ["Four Tet"]}, rows)
    # A coin flip between two levels takes the lower one, so it never lets a Concert in.
    assert levels == {"strong": 3, "tied": 1, "partial": 0}
    assert usage.cost == Decimal(1000) * jev.PRICE
    questions = cast(dict[str, object], sent[0]["questions"])
    assert set(questions) == set(rows)
    assert "Four Tet" in str(sent[0]["state"])


@pytest.mark.parametrize(
    "response", [httpx.Response(503), httpx.Response(200, json={"answers": "garbled"})]
)
async def test_a_failed_jev_answer_is_a_ranker_error(response: httpx.Response) -> None:
    client = jev.make_client("key", httpx.MockTransport(lambda _: response))
    graded = ranker.rows([candidate("x", 1, "one_hop")], {})
    with pytest.raises(ranker.RankerError):
        await ranker.grade(client, EMPTY, graded)


def reasons_model(reply: dict[str, str] | Exception) -> FunctionModel:
    def respond(messages: Sequence[ModelMessage], info: AgentInfo) -> ModelResponse:
        assert info.instructions == ranker.REASONS
        if isinstance(reply, Exception):
            raise reply
        prompt = next(
            json.loads(p.content)
            for m in messages
            for p in m.parts
            if isinstance(p, UserPromptPart) and isinstance(p.content, str)
        )
        assert [row["id"] for row in prompt["candidates"]] == ["1", "2"]
        reasons = [{"id": id_, "reason": reason} for id_, reason in reply.items()]
        return ModelResponse(parts=[TextPart(json.dumps({"reasons": reasons}))])

    return FunctionModel(respond)


async def test_reasons_come_back_in_row_order_and_a_skipped_row_gets_none() -> None:
    shown = list(
        ranker.rows([candidate("a", 1, "one_hop"), candidate("b", 1, "tags")], {}).values()
    )
    model = reasons_model({"2": "Dusty psych-funk", "99": "made up"})
    assert await ranker.explain(EMPTY, shown, model) == ["", "Dusty psych-funk"]


async def test_failed_reasons_are_a_ranker_error() -> None:
    shown = list(
        ranker.rows([candidate("a", 1, "one_hop"), candidate("b", 1, "tags")], {}).values()
    )
    with pytest.raises(ranker.RankerError):
        await ranker.explain(EMPTY, shown, reasons_model(RuntimeError("down")))
