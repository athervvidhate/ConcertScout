"""Audit contracts at the typed Concert boundary, with no provider or model calls."""

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from concert_scout import limits
from concert_scout.models import Artist, Concert
from evals.coverage import (
    AuditSettings,
    Candidate,
    Capture,
    Lookup,
    Reference,
    References,
    capture_sources,
    compare,
    main,
    parse_candidates,
    report,
)

DAY = dt.date(2026, 11, 8)


def reference() -> Reference:
    return Reference(
        id="venue:one",
        name="Headline",
        names=["Headline"],
        date=DAY,
        venue="Room",
        venue_aliases=["Room", "The Room"],
        city="Los Angeles",
        city_aliases=["Los Angeles"],
        source_url="https://venue.example/one",
        evidence_page="venue.html",
        keywords=["Headline"],
    )


def candidate(id: str = "ticketmaster:one", **changes: object) -> Candidate:
    concert = Concert(
        id=id,
        name="Headline: a tour",
        url="https://www.ticketweb.com/event/one",
        artists=[Artist(name="Headline")],
        date=DAY,
        venue="The Room",
        city="Los Angeles",
    ).model_copy(update=changes)
    return Candidate(concert=concert)


def capture(*candidates: Candidate, complete: bool = True) -> Capture:
    return Capture(
        captured_at=dt.datetime(2026, 11, 7, tzinfo=dt.UTC),
        seconds=1,
        references=References(
            start=DAY, end=DAY, country="US", state="CA", references=[reference()]
        ),
        lookups=[
            Lookup(
                provider="ticketmaster", keyword=key, complete=complete, candidates=list(candidates)
            )
            for key in ["Room", "Headline"]
        ],
    )


def test_external_checkout_and_repeated_queries_are_one_present_record() -> None:
    (finding,) = compare(capture(candidate()), "ticketmaster")
    assert finding.state == "present"
    assert finding.ids == ["ticketmaster:one"]
    assert finding.external_sellers == ["www.ticketweb.com"]
    assert not finding.multiple_listings


def test_multiple_sets_are_flagged_for_review_not_automatically_merged() -> None:
    (finding,) = compare(capture(candidate(), candidate("ticketmaster:two")), "ticketmaster")
    assert finding.state == "present"
    assert finding.multiple_listings
    assert len(finding.ids) == 2


def test_absence_requires_all_bounded_lookups_to_complete() -> None:
    assert compare(capture(), "ticketmaster")[0].state == "missing"
    assert compare(capture(complete=False), "ticketmaster")[0].state == "unresolved"
    partial = capture()
    partial.lookups.pop()
    assert compare(partial, "ticketmaster")[0].state == "unresolved"


def test_wrong_date_city_and_name_never_count_as_present() -> None:
    other_date = candidate(date=DAY + dt.timedelta(days=1))
    (finding,) = compare(capture(other_date), "ticketmaster")
    assert finding.state == "unresolved"
    assert finding.other_dates == [DAY + dt.timedelta(days=1)]
    assert compare(capture(candidate(city="Chicago")), "ticketmaster")[0].state == "missing"
    unrelated = candidate(name="Other", artists=[Artist(name="Other")])
    assert compare(capture(unrelated), "ticketmaster")[0].state == "unresolved"


def test_cancelled_and_outside_window_are_not_coverage_wins() -> None:
    cancelled = candidate().model_copy(update={"status": "cancelled"})
    assert compare(capture(cancelled), "ticketmaster")[0].state == "unresolved"
    outside = capture(candidate())
    outside.references.start = DAY + dt.timedelta(days=1)
    outside.references.end = outside.references.start
    assert compare(outside, "ticketmaster")[0].state == "out_of_scope"


def test_replay_uses_only_captured_data_and_preserves_errors(tmp_path: Path) -> None:
    before = capture(complete=False)
    before.lookups[0].error = "HTTP 429"
    path = tmp_path / "capture.json"
    path.write_text(before.model_dump_json())
    after = Capture.model_validate_json(path.read_text())
    assert report(after) == report(before)
    assert report(after)["providers"]["ticketmaster"]["errors"] == ["HTTP 429"]
    assert (
        json.loads(after.model_dump_json())["references"]["references"][0]["date"] == "2026-11-08"
    )


def test_reference_ids_and_window_cannot_be_ambiguous() -> None:
    data = capture().references.model_dump()
    data["references"] = [reference(), reference()]
    with pytest.raises(ValidationError, match="IDs must be unique"):
        References.model_validate(data)
    with pytest.raises(ValidationError, match="start must precede"):
        References(
            start=DAY + dt.timedelta(days=1), end=DAY, country="US", state="CA", references=[]
        )


def live_fields() -> dict[str, Any]:
    """Selected, unaltered fields from the dated live capture, not invented vendor JSON."""
    return json.loads(
        Path(__file__).with_name("fixtures").joinpath("coverage-sources.json").read_text()
    )


def test_real_source_fields_keep_ids_dates_links_and_missing_artists() -> None:
    fields = live_fields()
    tm, total = parse_candidates("ticketmaster", fields["ticketmaster"])
    assert total == 1
    concert = tm[0].concert
    assert concert.id.startswith("ticketmaster:")
    assert concert.date == dt.date(2026, 11, 14)
    assert concert.url == "https://www.ticketweb.com/event/jstjr-soma-mainstage-tickets/14285814"
    assert concert.venue == "SOMA - Mainstage"
    tf, total = parse_candidates("ticketfairy", fields["ticketfairy"])
    assert total == 7  # fixture deliberately retains one record from that seven-record page
    assert tf[0].concert.name == "Lotus @ Miner's Foundry"
    assert tf[0].concert.artists == []
    assert tf[0].concert.price is None
    assert tf[0].concert.time is None


@pytest.mark.asyncio
async def test_capture_stops_at_budget_and_incomplete_pages_do_not_prove_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_wait(_: object) -> None:
        pass

    monkeypatch.setattr(limits, "ticketmaster_call", no_wait)
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        # A selected-record real fixture is intentionally an incomplete page.
        return httpx.Response(200, json=live_fields()["ticketfairy"])

    result = await capture_sources(
        capture().references,
        AuditSettings(tm_key=SecretStr("private-test-key")),
        1,
        ["ticketfairy", "ticketmaster"],
        httpx.MockTransport(respond),
    )
    assert len(requests) == 1
    assert result.lookups[0].complete is False
    assert "count differs" in (result.lookups[0].error or "")
    assert all(f.state == "unresolved" for f in compare(result, "ticketmaster"))
    assert all(f.state == "unresolved" for f in compare(result, "ticketfairy"))


@pytest.mark.asyncio
async def test_failed_fetch_does_not_serialize_request_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_wait(_: object) -> None:
        pass

    monkeypatch.setattr(limits, "ticketmaster_call", no_wait)

    def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    result = await capture_sources(
        capture().references,
        AuditSettings(tm_key=SecretStr("private-test-key")),
        2,
        ["ticketmaster"],
        httpx.MockTransport(respond),
    )
    assert result.lookups[0].error == "HTTP 429"
    assert "private-test-key" not in result.model_dump_json()
    assert compare(result, "ticketmaster")[0].state == "unresolved"


def test_unknown_date_is_unresolved_even_when_queries_completed() -> None:
    assert compare(capture(candidate(date=None)), "ticketmaster")[0].state == "unresolved"
    assert compare(capture(candidate(city=None)), "ticketmaster")[0].state == "unresolved"


def test_replay_cli_never_opens_a_client_or_loads_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("replay attempted live access")

    path = tmp_path / "capture.json"
    path.write_text(capture(candidate()).model_dump_json())
    monkeypatch.setattr(sys, "argv", ["coverage", "replay", str(path)])
    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    monkeypatch.setattr("evals.coverage.AuditSettings", forbidden)
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["providers"]["ticketmaster"]["states"] == {"present": 1}
