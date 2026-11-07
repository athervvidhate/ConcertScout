import datetime as dt
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelResponse,
    TextPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage

from concert_scout.models import Artist, Concert, Recommendation
from concert_scout.ranker import Fit, Ranking
from evals import cases, compare, harness, judge, run, snapshots
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


def request(url: str, body: bytes = b"") -> httpx.Request:
    return httpx.Request("POST" if body else "GET", url, content=body)


def snapshot_with(records: dict[str, Recorded]) -> Snapshot:
    return Snapshot(
        id="s",
        text="Chicago",
        today=dt.date(2026, 11, 5),
        seconds_to_poster=3.0,
        lastfm_enabled=False,
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
    replay = ReplayModel(FunctionModel(answer), snapshot, live="none")

    result = await agent.run("Chicago", model=replay)

    assert result.output == "recorded"
    assert result.usage.input_tokens == 11
    with pytest.raises(UnexpectedModelBehavior):
        await agent.run("Detroit", model=replay)
    assert len(replay.misses) == 1


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
    labelled = Search(
        id="a", text="A", snapshot="a-1", must=["Altın Gün"], notes="Groove", judged=True
    )
    cases.save([labelled, Search(id="b", text="B")], path)

    loaded = cases.load(path)

    assert loaded[0] == labelled
    assert loaded[0].judged
    assert not loaded[1].judged


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
    search = Search(id="a", text="Chicago", snapshot="s", good=["One"], judged=True)

    report = await run.evaluate([search], None, live="none")

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
    search = Search(id="a", text="Chicago", snapshot="s", must=["One"], bad=["Two"], judged=True)

    report = await run.evaluate([search], None, live="none")

    case = report.cases[0]
    assert case.output.measures == Measures(0, 1, 1, 1, 1, 0)
    assert case.scores["must_found"].value == 1


async def test_recording_redacts_echoed_keys_but_does_not_change_the_live_response() -> None:
    # A generic HTTP echo exercises the recorder boundary, not a vendor response schema.
    secret = "sensitive/key+123"
    raw = f'{{"echo":"{secret}","encoded":"sensitive%2Fkey%2B123"}}'
    recorder = RecordingTransport(
        httpx.MockTransport(lambda _: httpx.Response(200, content=raw)), secrets=[secret]
    )
    response = await recorder.handle_async_request(
        request("https://example.com/echo?APIKEY=" + secret)
    )
    assert (await response.aread()).decode() == raw
    stored = str(recorder.records)
    assert secret not in stored and "sensitive%2Fkey%2B123" not in stored
    assert "[redacted]" in stored
    await recorder.aclose()


def test_snapshots_are_private_and_cannot_overwrite_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(snapshots, "SNAPSHOTS", tmp_path)
    original = snapshot_with({})
    snapshots.save(original)
    assert snapshots.path_for(original.id).stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        snapshots.save(original.model_copy(update={"text": "different"}))
    assert snapshots.load(original.id) == original


def test_an_explicit_all_neutral_judgment_is_complete_and_typos_are_not_silent() -> None:
    answers = iter(["typo", "neutral", "", ""])
    labels = judge.label_artists(["One", "Two"], lambda _: next(answers))
    completed = judge.apply_labels(
        Search(id="neutral", text="Sparse Search"), "snapshot", labels, ""
    )
    assert completed.judged
    assert not (completed.must or completed.good or completed.bad)
    assert not Search(id="draft", text="Sparse Search", snapshot="snapshot").judged


async def test_replay_restores_live_source_pacing_even_after_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from concert_scout import limits

    before = limits.SLOT_SECONDS, limits.MUSICBRAINZ_GAP

    async def fail(*_: Any, **__: Any) -> SearchRun:
        raise RuntimeError("replay failed")

    monkeypatch.setattr(harness, "run", fail)
    with pytest.raises(RuntimeError, match="replay failed"):
        await harness.replay(snapshot_with({}), None)
    assert (limits.SLOT_SECONDS, limits.MUSICBRAINZ_GAP) == before


async def test_offline_judging_needs_no_settings_and_refuses_changed_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def replay(_: Snapshot, settings: Any) -> tuple[SearchRun, list[str]]:
        assert settings is None
        return SearchRun(names=["One"]), []

    monkeypatch.setattr(harness, "replay", replay)
    answers = iter(["neutral", "", "Sparse"])
    completed = await judge.judge(
        Search(id="a", text="Chicago"), None, lambda _: next(answers), snapshot_with({})
    )
    assert completed.judged and completed.notes == "Sparse"
    with pytest.raises(ValueError, match="text differs"):
        await judge.judge(Search(id="a", text="Detroit"), None, lambda _: "", snapshot_with({}))


async def test_failed_paid_capture_still_records_spend_and_closes_source_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from collections.abc import AsyncIterator

    from fakeredis import FakeAsyncRedis
    from fastapi.sse import ServerSentEvent
    from pydantic_ai.usage import RunUsage

    from concert_scout import telemetry
    from concert_scout.pipeline import Services
    from tests.contracts import contract_model, forbidden_http, settings_with

    allocated: list[Services] = []
    original = harness.make_services

    def services(*args: Any, **kwargs: Any) -> Services:
        created = original(*args, **kwargs)
        allocated.append(created)
        return created

    async def fail(*_: Any) -> AsyncIterator[ServerSentEvent]:
        telemetry.record_usage(RunUsage(input_tokens=100, output_tokens=10, cost=Decimal("0.002")))
        raise RuntimeError("failed after model request")
        yield  # pragma: no cover

    monkeypatch.setattr(harness, "make_services", services)
    monkeypatch.setattr(harness, "stream_search", fail)
    async with FakeAsyncRedis() as ledger:
        with pytest.raises(RuntimeError, match="failed after model"):
            await harness.run(
                "Chicago",
                dt.date.today(),
                settings_with(),
                httpx.MockTransport(forbidden_http),
                contract_model(),
                ledger,
            )
        day = dt.datetime.now(dt.UTC).date()
        assert await ledger.get(f"spend:day:{day}") == b"2000"
    assert all(
        client.is_closed
        for client in (allocated[0].ticketmaster, allocated[0].geocoder, allocated[0].turnstile)
    )


async def test_a_pipeline_error_is_a_failed_case_not_a_successful_empty_poster(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def replay(*_: Any) -> tuple[SearchRun, list[str]]:
        return SearchRun(error="ticketmaster_unavailable"), []

    monkeypatch.setattr(snapshots, "load", load_empty)
    monkeypatch.setattr(run.harness, "replay", replay)
    report = await run.evaluate(
        [Search(id="a", text="Chicago", snapshot="s", judged=True)], None, live="none"
    )
    assert not report.cases
    assert "no quality score" in report.failures[0].error_message


def compared_snapshot(picks: dict[str, int]) -> Snapshot:
    def event(id_: str) -> dict[str, Any]:
        return {
            "id": id_,
            "name": f"Show {id_}",
            "url": "https://tickets.example",
            "dates": {"start": {}},
            "_embedded": {"attractions": [{"name": f"Artist {id_}"}]},
        }

    body = {"_embedded": {"events": [event(id_) for id_ in ("a", "b", "c")]}}
    ranking = Ranking(fits=[Fit(id=i, level=s, reason="Why") for i, s in picks.items()])
    answer = ModelResponse(parts=[TextPart(ranking.model_dump_json())])
    return Snapshot(
        id="case",
        text="x",
        today=dt.date(2026, 11, 5),
        seconds_to_poster=None,
        lastfm_enabled=False,
        records={
            "GET https://app.ticketmaster.com/events.json x": Recorded(
                status=200, content_type="application/json", body=json.dumps(body)
            )
        },
        answers={"ranker": ModelMessagesTypeAdapter.dump_json([answer]).decode()},
    )


def test_compare_counts_artists_the_poster_would_show() -> None:
    change = compare.compare(
        "case",
        compared_snapshot({"a": 3, "b": 2, "c": 1}),
        compared_snapshot({"a": 2, "c": 3, "unknown": 3}),
    )
    assert change.before == {"Artist a": 3, "Artist b": 2}
    assert change.after == {"Artist a": 2, "Artist c": 3}
    assert change.overlap == pytest.approx(1 / 3)
    assert "lost Artist b (2)" in compare.report([change])


def tags_snapshot() -> Snapshot:
    def recorded(mbids: list[str], found: list[str]) -> tuple[str, Recorded]:
        url = httpx.URL("https://api.listenbrainz.org/1/metadata/artist/")
        request = httpx.Request("GET", url.copy_merge_params({"artist_mbids": ",".join(mbids)}))
        body = [{"artist_mbid": m, "tag": {"artist": [{"tag": f"t-{m}"}]}} for m in found]
        return snapshots.request_key(request), Recorded(
            status=200, content_type="application/json", body=json.dumps(body)
        )

    records = dict([recorded(["a", "b"], ["a", "b"]), recorded(["c", "d"], ["c"])])
    return Snapshot(
        id="tags",
        text="x",
        today=dt.date(2026, 11, 5),
        seconds_to_poster=None,
        lastfm_enabled=False,
        records=records,
        answers={},
    )


async def test_replay_answers_any_batch_of_recorded_artists() -> None:
    transport = ReplayTransport(tags_snapshot())
    async with httpx.AsyncClient(transport=transport) as client:
        mixed = await client.get(
            "https://api.listenbrainz.org/1/metadata/artist/", params={"artist_mbids": "d,a,c"}
        )
        unknown = await client.get(
            "https://api.listenbrainz.org/1/metadata/artist/", params={"artist_mbids": "a,z"}
        )
    assert [item["artist_mbid"] for item in mixed.json()] == ["a", "c"]
    assert unknown.status_code == 404
    assert len(transport.misses) == 1
