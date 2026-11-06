import datetime as dt
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage

from concert_scout.models import Artist, Concert, Recommendation
from evals import cases, judge, run, snapshots
from evals.cases import Search
from evals.harness import SearchRun
from evals.metrics import Measures
from evals.snapshots import (
    Recorded,
    RecordingModel,
    RecordingTransport,
    ReplayModel,
    ReplayTransport,
    Snapshot,
)
from tests.conftest import tm_body, tm_record


def request(url: str, body: bytes = b"") -> httpx.Request:
    return httpx.Request("POST" if body else "GET", url, content=body)


def snapshot_with(records: dict[str, Recorded]) -> Snapshot:
    return Snapshot(
        id="s",
        text="Chicago",
        today=dt.date(2026, 11, 5),
        seconds_to_poster=3.0,
        records=records,
        answers={},
    )


async def test_recording_keeps_api_keys_out_and_replay_answers_the_same_request() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    url = "https://app.ticketmaster.com/discovery/v2/events.json?city=Chicago&apikey=secret"
    recording = RecordingTransport(httpx.MockTransport(handler))
    await recording.handle_async_request(request(url))
    assert "secret" not in str(recording.records)

    replay = ReplayTransport(snapshot_with(recording.records))
    response = await replay.handle_async_request(request(url.replace("secret", "other-key")))

    assert await response.aread() == b'{"ok":true}'
    assert replay.misses == []


async def test_replay_reports_a_request_it_never_saw() -> None:
    replay = ReplayTransport(snapshot_with({}))

    response = await replay.handle_async_request(request("https://example.com/new"))

    assert response.status_code == 404
    assert len(replay.misses) == 1


async def test_a_changed_request_body_is_a_different_request() -> None:
    url = "https://api.anthropic.com/v1/messages"

    assert snapshots.request_key(request(url, b"a")) != snapshots.request_key(request(url, b"b"))


async def test_a_recorded_model_answer_replays_with_its_usage_and_a_new_question_misses() -> None:
    def answer(_: list[ModelMessage], __: AgentInfo) -> ModelResponse:
        usage = RequestUsage(input_tokens=11, output_tokens=7)
        return ModelResponse(parts=[TextPart("recorded")], usage=usage)

    agent = Agent()
    recording = RecordingModel(FunctionModel(answer))
    await agent.run("Chicago", model=recording)
    snapshot = snapshot_with({}).model_copy(update={"answers": recording.answers})
    replay = ReplayModel(FunctionModel(answer), snapshot, live=False)

    result = await agent.run("Chicago", model=replay)

    assert result.output == "recorded"
    assert result.usage.input_tokens == 11
    with pytest.raises(UnexpectedModelBehavior):
        await agent.run("Detroit", model=replay)
    assert len(replay.misses) == 1


async def test_a_live_replay_asks_the_real_model() -> None:
    def answer(_: list[ModelMessage], __: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart("live")])

    replay = ReplayModel(FunctionModel(answer), snapshot_with({}), live=True)

    result = await Agent().run("Chicago", model=replay)

    assert result.output == "live"
    assert replay.misses == []


def test_source_concerts_come_from_ticketmaster_answers_only() -> None:
    answer = Recorded(
        status=200, content_type="application/json", body=json.dumps(tm_body(tm_record()))
    )
    other = Recorded(status=200, content_type="application/json", body="{}")
    snapshot = snapshot_with(
        {"GET https://x/discovery/v2/events.json a": answer, "GET https://y/other b": other}
    )

    assert [c.id for c in snapshots.source_concerts(snapshot)] == ["vvG18Z_ueUZbii"]


def test_label_artists_records_each_answer_and_adds_missed_must_artists() -> None:
    answers = iter(["m", "g", "b", "", "Altın Gün, Men I Trust"])

    labels = judge.label_artists(["One", "Two", "Three", "Four"], lambda _: next(answers))

    assert labels.must == ["One", "Altın Gün", "Men I Trust"]
    assert labels.good == ["Two"]
    assert labels.bad == ["Three"]


def test_the_sample_puts_the_poster_first_and_stops_at_twenty() -> None:
    names = [f"Artist {n}" for n in range(30)]

    chosen = judge.sample(["Headliner", "Artist 2"], names)

    assert chosen[:3] == ["Headliner", "Artist 2", "Artist 0"]
    assert len(chosen) == 20


def test_cases_round_trip_and_only_labelled_searches_count_as_judged(tmp_path: Path) -> None:
    path = tmp_path / "searches.yaml"
    labelled = Search(id="a", text="A", snapshot="a-1", must=["Altın Gün"], notes="Groove")
    cases.save([labelled, Search(id="b", text="B")], path)

    loaded = cases.load(path)

    assert loaded[0] == labelled
    assert loaded[0].judged
    assert not loaded[1].judged


def test_the_drafted_search_set_holds_twenty_unjudged_searches() -> None:
    searches = cases.load()

    assert len(searches) == 20
    assert len({search.id for search in searches}) == 20


def scored(measures: Measures, seconds: float | None = 2.0, cost: str = "0.001") -> run.Scored:
    return run.Scored(SearchRun(cost=Decimal(cost)), measures, seconds)


def test_the_summary_reports_every_measure_against_its_target() -> None:
    good = Measures(0, 1, 1, 6, 8, 0)
    poor = Measures(1, 0, 1, 1, 8, 1)

    lines = run.summary([scored(good), scored(poor, seconds=20.0, cost="0.003")])

    assert lines == [
        "Bad Artists on a Poster:  1  (MISSED, target 0)",
        "Must Artists found:       50%  (MISSED, at least 90%)",
        "Poster judged good:       44%  (MISSED, at least 60%)",
        "Invented or unknown IDs:  1  (MISSED, target 0)",
        "Time to poster, p95:      20.0s as captured, cold  (MISSED, under 15s)",
        "Cost per Search:          $0.002000",
    ]


def load_empty(_: str) -> Snapshot:
    return snapshot_with({})


async def test_a_run_reports_a_snapshot_miss_instead_of_a_silent_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(snapshots, "load", load_empty)
    search = Search(id="a", text="Chicago", snapshot="s", good=["One"])

    report = await run.evaluate([search], None, live_model=False)

    assert report.cases == []
    assert "not in the Snapshot" in report.failures[0].error_message


async def test_a_replayed_search_scores_the_poster_against_source_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    concert = Concert(id="1", name="C", url="https://x", artists=[Artist(name="One")])

    async def replay(*_: Any) -> tuple[SearchRun, list[str]]:
        return SearchRun(recommendations=[Recommendation(concert=concert, reason="fit")]), []

    def source(_: Snapshot) -> list[Concert]:
        return [concert]

    monkeypatch.setattr(snapshots, "load", load_empty)
    monkeypatch.setattr(snapshots, "source_concerts", source)
    monkeypatch.setattr(run.harness, "replay", replay)
    search = Search(id="a", text="Chicago", snapshot="s", must=["One"], bad=["Two"])

    report = await run.evaluate([search], None, live_model=False)

    case = report.cases[0]
    assert case.output.measures == Measures(0, 1, 1, 1, 1, 0)
    assert case.scores["must_found"].value == 1
