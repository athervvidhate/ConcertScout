import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from concert_scout import ranker
from concert_scout.names import normalize
from evals import grade, silver, snapshots
from evals.grade import Grader, Row
from evals.scorecard import Card, jaccard, mean_overlap
from evals.snapshots import RecordingModel, ReplayModel, Snapshot


def card(posters: list[set[str]], **fields: object) -> Card:
    defaults: dict[str, object] = {"shortlists": 1, "failures": 0}
    return Card("case", [frozenset(p) for p in posters], **(defaults | fields))  # pyright: ignore[reportArgumentType]


def test_two_empty_posters_agree() -> None:
    assert jaccard(frozenset(), frozenset()) == 1.0


def test_overlap_averages_every_pair() -> None:
    a, b, c = frozenset({"x", "y"}), frozenset({"x"}), frozenset({"z"})
    assert mean_overlap([a, b, c]) == pytest.approx(1 / 6)


def test_silver_recall_counts_silver_artists_the_shortlist_missed() -> None:
    scored = card(
        [{"seed", "a"}],
        seeds=frozenset({"seed"}),
        silver={"a", "b", "c"},
        playing={"seed", "a", "b", "z"},
        shortlisted={"seed", "a"},
    )
    # a and b are silver and playing; b never reached the shortlist, and still counts as missed.
    assert scored.silver_recall() == 0.5


def test_recall_is_capped_by_the_places_seeds_leave() -> None:
    available = {f"artist {n}" for n in range(20)}
    assert silver.recall({"artist 1", "artist 2"}, available, seeds=6) == 1.0
    assert silver.recall(set(), set(), seeds=0) is None


def test_graded_measures_leave_seeds_out() -> None:
    scored = card(
        [{"seed", "good", "miss"}],
        seeds=frozenset({"seed"}),
        levels={"seed": 3, "good": 3, "miss": 0, "strong": 3},
    )
    assert scored.graded_precision() == 0.5
    assert scored.graded_recall() == 0.5


def test_grader_agreement_sides_with_human_labels() -> None:
    levels = {normalize("Altın Gün"): 3, "weezer": 2, "nickelback": 0}
    assert grade.agreement(levels, good=["Altın Gün"], bad=["Weezer", "Nickelback"]) == 2 / 3
    assert grade.agreement(levels, good=[], bad=[]) is None


async def test_grader_asks_only_for_artists_not_yet_graded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(grade, "CACHE", tmp_path / "grades.json")
    asked: list[list[str]] = []

    def answer(messages: list[ModelMessage], _: AgentInfo) -> ModelResponse:
        part = messages[-1].parts[-1]
        assert isinstance(part, UserPromptPart) and isinstance(part.content, str)
        prompt = json.loads(part.content)
        names = [row["artist"] for row in prompt["artists"]]
        asked.append(names)
        grades = [{"artist": name, "level": 2} for name in names]
        return ModelResponse(parts=[TextPart(json.dumps({"grades": grades}))])

    grader = Grader("key")
    grader.model = FunctionModel(answer)  # pyright: ignore[reportAttributeAccessIssue]
    first = await grader.grade("Dreamy guitar", [Row(artist="Men I Trust", genre=None)])
    second = await grader.grade(
        "Dreamy guitar",
        [Row(artist="Men I Trust", genre=None), Row(artist="Beach House", genre="Rock")],
    )

    assert first == {"men i trust": 2}
    assert second == {"men i trust": 2, "beach house": 2}
    assert asked == [["Men I Trust"], ["Beach House"]]


def snapshot(answers: dict[str, str]) -> Snapshot:
    return Snapshot.model_validate(
        {
            "id": "s",
            "text": "t",
            "today": "2026-11-07",
            "lastfm_enabled": False,
            "seconds_to_poster": None,
            "records": {},
            "answers": answers,
        }
    )


async def test_ranker_mode_replays_the_interpreter_and_asks_the_ranker_afresh() -> None:
    def recorded(_: list[ModelMessage], __: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart("recorded")])

    def live(_: list[ModelMessage], __: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart("live")])

    interpreter = Agent(instructions="Read the Search.")
    ranking = Agent(instructions=ranker.INSTRUCTIONS)
    recording = RecordingModel(FunctionModel(recorded))
    await interpreter.run("Chicago", model=recording)
    await ranking.run("rows", model=recording)
    replay = ReplayModel(FunctionModel(live), snapshot(recording.answers), live="ranker")

    assert (await interpreter.run("Chicago", model=replay)).output == "recorded"
    assert (await ranking.run("rows", model=replay)).output == "live"


def test_interpretation_reads_the_recorded_reading_of_the_search() -> None:
    reading = {
        "artists": ["Khruangbin"],
        "descriptors": [],
        "tags": [],
        "place": "Chicago",
        "start": None,
        "end": None,
    }
    answer = json.dumps(
        [{"kind": "response", "parts": [{"part_kind": "text", "content": json.dumps(reading)}]}]
    )
    found = snapshots.interpretation(snapshot({"a": answer}))
    assert found is not None and found.artists == ["Khruangbin"]
    assert snapshots.interpretation(snapshot({})) is None


def test_cost_starts_at_zero() -> None:
    assert card([set()]).cost == Decimal(0)
