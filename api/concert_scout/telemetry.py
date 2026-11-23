"""Safe Search telemetry. Only fixed span names and numeric usage leave this module."""

import logging
import time
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from decimal import Decimal

from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from pydantic_ai.usage import RunUsage

from concert_scout import limits

logger = logging.getLogger(__name__)


class LogExporter(SpanExporter):
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        for span in spans:
            logger.warning(
                "search span=%s trace=%032x duration_ms=%.2f attributes=%s",
                span.name,
                span.context.trace_id if span.context else 0,
                ((span.end_time or 0) - (span.start_time or 0)) / 1_000_000,
                dict(span.attributes or {}),
            )
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass


provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(LogExporter()))
tracer = provider.get_tracer(__name__)


@dataclass
class SearchUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost: Decimal = Decimal(0)
    complete: bool = True
    # Seconds spent in each pipeline step, so a slow Search shows where its time went.
    steps: dict[str, float] = field(default_factory=dict[str, float])
    cache_hits: int = 0
    cache_misses: int = 0
    pool_total: int = 0
    shortlist_total: int = 0
    picks_total: int = 0
    started: float = field(default_factory=time.perf_counter)

    def total_ms(self) -> float:
        return round(max(0.0, (time.perf_counter() - self.started) * 1000.0), 1)


_current: ContextVar[SearchUsage | None] = ContextVar("search_usage", default=None)


def record_cache(hit: bool) -> None:
    """Count cache hits and misses for anonymized Engineering Lab telemetry."""
    if total := _current.get():
        if hit:
            total.cache_hits += 1
        else:
            total.cache_misses += 1


def record_funnel(
    *,
    pool_total: int | None = None,
    shortlist_total: int | None = None,
    picks_total: int | None = None,
) -> None:
    """Record pool, shortlist, and pick counts for the current Search."""
    if total := _current.get():
        if pool_total is not None:
            total.pool_total = pool_total
        if shortlist_total is not None:
            total.shortlist_total = shortlist_total
        if picks_total is not None:
            total.picks_total = picks_total


def step_timings_ms() -> dict[str, float]:
    """Snapshot recorded step timings in milliseconds for the current Search."""
    total = _current.get()
    if total is None:
        return {}
    return {name: round(max(0.0, seconds * 1000.0), 1) for name, seconds in total.steps.items()}


def record_usage(usage: RunUsage) -> None:
    """Accumulate actual model usage; missing prices or usage remain explicitly unknown."""
    total = _current.get()
    span = trace.get_current_span()
    span.set_attribute("input_tokens", usage.input_tokens)
    span.set_attribute("output_tokens", usage.output_tokens)
    if usage.cost is not None:
        span.set_attribute("cost_usd", float(usage.cost))
    if total is not None:
        total.input_tokens += usage.input_tokens
        total.output_tokens += usage.output_tokens
        if usage.cost is None or usage.unmeasured_requests:
            total.complete = False
        else:
            total.cost += usage.cost


def record_cost(cost: Decimal) -> None:
    """A priced call outside pydantic-ai, such as Jev, which bills by the request."""
    trace.get_current_span().set_attribute("jev_cost_usd", float(cost))
    if total := _current.get():
        total.cost += cost


def record_embedding(tokens: int) -> None:
    """Gemini's embedding API reports no usage, so callers pass an estimate of the input tokens."""
    cost = Decimal(tokens) * limits.EMBEDDING_USD_PER_MILLION_TOKENS / limits.MICRODOLLARS
    span = trace.get_current_span()
    span.set_attribute("embedding_tokens", tokens)
    span.set_attribute("embedding_cost_usd", float(cost))
    if total := _current.get():
        total.input_tokens += tokens
        total.cost += cost


@contextmanager
def step(name: str) -> Generator[None]:
    # Exception messages and stack traces can contain Search text or source data.
    started = time.perf_counter()
    try:
        with tracer.start_as_current_span(
            name, record_exception=False, set_status_on_exception=False
        ):
            yield
    finally:
        if total := _current.get():
            total.steps[name] = total.steps.get(name, 0) + time.perf_counter() - started


@contextmanager
def search() -> Generator[SearchUsage]:
    usage = SearchUsage()
    token = _current.set(usage)
    try:
        with tracer.start_as_current_span(
            "search", record_exception=False, set_status_on_exception=False
        ) as span:
            try:
                yield usage
            finally:
                span.set_attribute("input_tokens", usage.input_tokens)
                span.set_attribute("output_tokens", usage.output_tokens)
                span.set_attribute("cost_complete", usage.complete)
                if usage.complete:
                    span.set_attribute("cost_usd", float(usage.cost))
    finally:
        _current.reset(token)
