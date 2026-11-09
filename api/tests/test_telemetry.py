from decimal import Decimal

import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic_ai.usage import RunUsage

from concert_scout import telemetry
from tests.contracts import install_sources
from tests.test_app import api_for


async def test_search_spans_never_include_taste_or_spotify_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_sources(monkeypatch)
    exporter = InMemorySpanExporter()
    telemetry.provider.add_span_processor(SimpleSpanProcessor(exporter))
    secret = "private taste and Spotify listening history"
    async with api_for() as api:
        await api.post("/search", json={"text": secret, "token": "token", "time_zone": "UTC"})
    spans = exporter.get_finished_spans()
    assert {span.name for span in spans} >= {"search", "interpret", "resolve_place", "pool"}
    assert secret not in repr([(s.name, s.attributes, s.events, s.status) for s in spans])
    assert all(s.end_time and s.start_time and s.end_time >= s.start_time for s in spans)


def test_error_span_does_not_record_exception_text() -> None:
    exporter = InMemorySpanExporter()
    telemetry.provider.add_span_processor(SimpleSpanProcessor(exporter))
    secret = "private Taste and Spotify data"
    with pytest.raises(ValueError), telemetry.search(), telemetry.step("interpret"):
        raise ValueError(secret)
    spans = exporter.get_finished_spans()
    assert secret not in repr([(s.attributes, s.events, s.status) for s in spans])


def test_usage_aggregates_and_marks_unknown_cost() -> None:
    with telemetry.search() as total, telemetry.step("interpret"):
        telemetry.record_usage(RunUsage(input_tokens=100, output_tokens=20, cost=Decimal("0.001")))
        telemetry.record_usage(RunUsage(input_tokens=5, output_tokens=1))
        assert (total.input_tokens, total.output_tokens, total.cost, total.complete) == (
            105,
            21,
            Decimal("0.001"),
            False,
        )
