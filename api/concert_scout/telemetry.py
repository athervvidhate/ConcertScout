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


_current: ContextVar[SearchUsage | None] = ContextVar("search_usage", default=None)


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
