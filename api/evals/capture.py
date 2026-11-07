"""Capture real Searches before human judging: `uv run python -m evals.capture [id ...]`.

Paid and serialized. Defaults to one unjudged Search, stopping before the next Search when the
measured batch cost reaches --max-cost. A single in-flight Search can exceed that threshold.
"""

import argparse
import asyncio
import datetime as dt
import json
import os
from decimal import Decimal
from uuid import uuid4

from concert_scout.config import Settings
from evals import cases, harness, snapshots


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "ids", nargs="*", help="Search IDs; otherwise unjudged Searches in file order."
    )
    parser.add_argument(
        "--limit", type=int, default=1, help="Maximum Searches to capture (default1)."
    )
    parser.add_argument(
        "--max-cost", type=Decimal, default=Decimal("0.05"), help="Measured batch USD."
    )
    args = parser.parse_args()
    searches = cases.load()
    if unknown := set(args.ids) - {s.id for s in searches}:
        parser.error("Unknown Search IDs: " + ", ".join(sorted(unknown)))
    if args.limit < 1 or not args.max_cost.is_finite() or args.max_cost <= 0:
        parser.error("--limit and --max-cost must be positive")
    chosen = (
        [s for s in searches if s.id in args.ids]
        if args.ids
        else [s for s in searches if not s.judged]
    )
    chosen = chosen[: args.limit]
    if not chosen:
        print("Nothing to capture.")
        return
    settings = Settings()  # pyright: ignore[reportCallIssue]
    total = Decimal(0)
    entries: list[dict[str, str | int | float | bool | None]] = []
    batch_id = dt.datetime.now(dt.UTC).strftime("batch-%Y-%m-%d-%H%M%S-") + uuid4().hex[:8]
    failed = False
    snapshots.SNAPSHOTS.mkdir(exist_ok=True)
    report = snapshots.SNAPSHOTS / f"{batch_id}.json"
    for search in chosen:
        if total >= args.max_cost:
            print("Measured batch threshold reached; not starting another Search.")
            failed = True
            break
        print(f"Capturing {search.id}...", flush=True)
        snapshot, result = await harness.capture(search.id, search.text, settings)
        snapshots.save(snapshot)
        total += result.cost
        entries.append(
            {
                "id": search.id,
                "snapshot": snapshot.id,
                "seconds_to_poster": result.seconds_to_poster,
                "cost_usd": str(result.cost),
                "cost_complete": result.cost_complete,
                "recommendations": len(result.recommendations),
                "candidates": len(result.names),
                "error": result.error,
            }
        )
        # Update the private report after each completed Search; labels/YAML are untouched.
        descriptor = os.open(report, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w") as output:
            json.dump({"captures": entries, "total_cost_usd": str(total)}, output, indent=2)
        print(
            f"  {snapshot.id}: {len(result.recommendations)} picks, "
            f"{result.seconds_to_poster}s, ${result.cost}; error={result.error}",
            flush=True,
        )
        if result.error:
            failed = True
        if not result.cost_complete:
            print("Cost is incomplete; stopping before another paid Search.")
            failed = True
            break
    print(f"Captured {len(entries)}/{len(chosen)}; measured total ${total}. Report: {report}")
    print("No relevance labels were written. Judge with: evals.judge <id> --snapshot <snapshot>")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
