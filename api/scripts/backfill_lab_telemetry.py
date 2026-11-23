"""Backfill anonymized numeric Search telemetry from historical API logs into Supabase.

Parses `search span=<name> trace=<id> duration_ms=<ms> attributes=<dict>` lines emitted by
`telemetry.LogExporter` (e.g. from `vercel logs concert-scout-api`), groups spans by trace ID,
validates them through `lab.SearchMetrics` (strictly numeric, zero PII), and inserts them into
`public.search_telemetry` with `source='backfill'`.

Usage:
  cd api
  vercel logs concert-scout-api | uv run python scripts/backfill_lab_telemetry.py --dry-run
  vercel logs concert-scout-api | uv run python scripts/backfill_lab_telemetry.py --apply
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import datetime as dt
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from concert_scout import lab
from concert_scout.config import Settings
from concert_scout.sources import supabase

SPAN_RE = re.compile(
    r"search span=(?P<name>[a-z_]+) trace=(?P<trace>[0-9a-f]{32}) "
    r"duration_ms=(?P<ms>[0-9]+(?:\.[0-9]+)?) attributes=(?P<attrs>\{.*\})"
)
ISO_PREFIX_RE = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
)


@dataclass
class _TraceBucket:
    total_ms: float | None = None
    steps_ms: dict[str, float] = field(default_factory=dict[str, float])
    cost_usd: float = 0.0
    cost_complete: bool = True
    recorded_at: str | None = None


def parse_log_lines(
    lines: Iterable[str],
    *,
    default_now: dt.datetime | None = None,
) -> list[lab.SearchMetrics]:
    """Parse `search span=...` log lines into validated numeric `SearchMetrics` rows."""
    fallback_bucket = lab.hour_bucket(default_now)
    traces: dict[str, _TraceBucket] = {}

    for line in lines:
        match = SPAN_RE.search(line)
        if not match:
            continue
        name = match.group("name")
        trace_id = match.group("trace")
        duration_ms = float(match.group("ms"))
        bucket = traces.setdefault(trace_id, _TraceBucket())

        if bucket.recorded_at is None:
            ts_match = ISO_PREFIX_RE.search(line)
            if ts_match:
                try:
                    raw_ts = ts_match.group("ts").replace(" ", "T")
                    parsed = dt.datetime.fromisoformat(raw_ts)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=dt.UTC)
                    bucket.recorded_at = lab.hour_bucket(parsed)
                except ValueError:
                    pass

        try:
            raw_attrs: object = ast.literal_eval(match.group("attrs"))
        except (SyntaxError, ValueError):
            raw_attrs = {}
        attrs: dict[str, Any] = (
            cast(dict[str, Any], raw_attrs) if isinstance(raw_attrs, dict) else {}
        )

        if name == "search":
            bucket.total_ms = round(max(0.0, duration_ms), 1)
            cost_complete: object = attrs.get("cost_complete")
            if isinstance(cost_complete, bool):
                bucket.cost_complete = cost_complete
            cost_usd: object = attrs.get("cost_usd")
            if (
                isinstance(cost_usd, (int, float))
                and not isinstance(cost_usd, bool)
                and cost_usd >= 0
            ):
                bucket.cost_usd = round(float(cost_usd), 6)
        elif name in lab.ALLOWED_STEPS:
            bucket.steps_ms[name] = round(bucket.steps_ms.get(name, 0.0) + max(0.0, duration_ms), 1)

    rows: list[lab.SearchMetrics] = []
    for bucket in traces.values():
        if bucket.total_ms is None:
            continue
        rows.append(
            lab.SearchMetrics(
                total_ms=bucket.total_ms,
                steps_ms=bucket.steps_ms,
                cost_usd=bucket.cost_usd,
                cost_complete=bucket.cost_complete,
                recorded_at=bucket.recorded_at or fallback_bucket,
            )
        )
    return rows


async def _apply(rows: list[lab.SearchMetrics], batch_size: int = 100) -> int:
    settings = Settings()  # type: ignore[call-arg]
    if not (settings.supabase_url and settings.supabase_secret_key):
        raise SystemExit("SUPABASE_URL and SUPABASE_SECRET_KEY are required for --apply.")
    inserted = 0
    async with supabase.make_client(settings.supabase_url) as client:
        for start in range(0, len(rows), batch_size):
            chunk = rows[start : start + batch_size]
            inserted += await lab.insert_telemetry_rows(
                client, settings.supabase_secret_key, chunk, source="backfill"
            )
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill anonymized Search telemetry from API logs into Supabase."
    )
    parser.add_argument("file", nargs="?", type=Path, help="Log file path (defaults to stdin).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run", action="store_true", help="Parse and summarize without writing."
    )
    group.add_argument("--apply", action="store_true", help="Write parsed rows into Supabase.")
    args = parser.parse_args()

    lines = (
        args.file.read_text(encoding="utf-8", errors="replace").splitlines()
        if args.file
        else sys.stdin
    )
    rows = parse_log_lines(lines)
    p50 = lab.percentile([r.total_ms for r in rows], 50)
    p95 = lab.percentile([r.total_ms for r in rows], 95)
    print(f"Parsed {len(rows)} completed Searches (p50={p50} ms, p95={p95} ms).")
    if args.dry_run or not rows:
        return
    inserted = asyncio.run(_apply(rows))
    print(f"Inserted {inserted} anonymized rows into public.search_telemetry.")


if __name__ == "__main__":
    main()
