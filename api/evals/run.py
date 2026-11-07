"""Score the pipeline on judged Searches: `uv run python -m evals.run [--live ranker|all]`.

By default everything replays from Snapshots, offline and free, which proves the harness and
repeats the captured answers. After changing the ranker, use `--live ranker`, which keeps the
recorded reading of the Search. After changing the interpreter, use `--live all`. Both call the
real model and cost money.
"""

import argparse
import asyncio
import math
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path

from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext
from pydantic_evals.reporting import EvaluationReport

from concert_scout.config import Settings
from evals import cases, harness, snapshots
from evals.cases import Search
from evals.harness import SearchRun
from evals.metrics import Measures, measure
from evals.snapshots import Live


@dataclass
class Scored:
    run: SearchRun
    measures: Measures
    seconds_to_poster: float | None


class SnapshotMiss(Exception):
    """The pipeline asked for something the Snapshot never saw."""


@dataclass
class JudgedPoster(Evaluator[Search, Scored, None]):
    def evaluate(self, ctx: EvaluatorContext[Search, Scored, None]) -> dict[str, int | float]:
        scores: dict[str, int | float] = dict(asdict(ctx.output.measures))
        scores["cost_usd"] = float(ctx.output.run.cost)
        return scores


def scorer(settings: Settings | None, live: Live):
    async def score(search: Search) -> Scored:
        assert search.snapshot
        snapshot = snapshots.load(search.snapshot)
        result, misses = await harness.replay(snapshot, settings, live)
        if misses:
            raise SnapshotMiss(
                f"{len(misses)} requests are not in the Snapshot, such as {misses[0]}. "
                "Use --live if only model requests changed, or judge the Search again."
            )
        if result.error:
            raise RuntimeError(f"Search ended with {result.error}; no quality score was assigned")
        measures = measure(
            result.recommendations,
            snapshots.source_concerts(snapshot),
            search.must,
            search.good,
            search.bad,
        )
        return Scored(result, measures, snapshot.seconds_to_poster)

    return score


def p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * 0.95) - 1]


def summary(scored: list[Scored]) -> list[str]:
    """One line per measure in docs/specs/06-evals.md, with its target."""
    measures = [item.measures for item in scored]
    must_total = sum(m.must_total for m in measures)
    must_share = sum(m.must_found for m in measures) / must_total if must_total else 1.0
    shown = sum(m.recommendations for m in measures)
    good_share = sum(m.judged_good_recommendations for m in measures) / shown if shown else 0.0
    bad = sum(m.bad_artists for m in measures)
    invented = sum(m.invented_or_unknown for m in measures)
    times = [item.seconds_to_poster for item in scored if item.seconds_to_poster is not None]
    slowest = p95(times) if times else None
    costs = [item.run.cost for item in scored]
    complete = all(item.run.cost_complete for item in scored)
    mean_cost = sum(costs, Decimal(0)) / len(costs)

    def mark(met: bool) -> str:
        return "met" if met else "MISSED"

    time_line = "no Poster arrived"
    if slowest is not None:
        time_line = f"{slowest:.1f}s as captured, cold  ({mark(slowest < 15)}, under 15s)"
    return [
        f"Bad Artists on a Poster:  {bad}  ({mark(bad == 0)}, target 0)",
        (
            f"Must Artists found:       {must_share:.0%}  ({mark(must_share >= 0.9)}, at least 90%)"
            if must_total
            else "Must Artists found:       no must labels; recall not measurable"
        ),
        f"Poster judged good:       {good_share:.0%}  ({mark(good_share >= 0.6)}, at least 60%)",
        f"Invented or unknown IDs:  {invented}  ({mark(invented == 0)}, target 0)",
        f"Time to poster, p95:      {time_line}",
        f"Cost per Search:          ${mean_cost:.6f}{'' if complete else ' (incomplete)'}",
    ]


def print_report(report: EvaluationReport[Search, Scored, None], total: int) -> None:
    scored = [case.output for case in report.cases]
    print(f"{len(report.cases)} of {total} Searches scored\n")
    for case in report.cases:
        m = case.output.measures
        print(
            f"  {case.name}: {m.recommendations} on Poster, {m.bad_artists} bad, "
            f"{m.must_found}/{m.must_total} must, {m.judged_good_recommendations} good, "
            f"{m.invented_or_unknown} invented"
        )
    for failure in report.failures:
        print(f"  {failure.name} FAILED: {failure.error_message}")
    print()
    if scored:
        print("\n".join(summary(scored)))


async def evaluate(
    searches: list[Search], settings: Settings | None, live: Live
) -> EvaluationReport[Search, Scored, None]:
    dataset = Dataset[Search, Scored, None](
        name="concert-scout",
        cases=[Case(name=search.id, inputs=search) for search in searches],
        evaluators=[JudgedPoster()],
    )
    return await dataset.evaluate(scorer(settings, live), max_concurrency=1, progress=False)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        choices=["none", "ranker", "all"],
        default="none",
        help="Call the real model for the ranker or for every request. Costs money.",
    )
    parser.add_argument("--searches", type=Path, default=cases.SEARCHES, help="Judged Search YAML.")
    arguments = parser.parse_args()
    searches = cases.load(arguments.searches)
    judged = [s for s in searches if s.judged and snapshots.path_for(s.snapshot or "").exists()]
    if not judged:
        print(f"No judged Searches yet, out of {len(searches)}. Run evals.judge first.")
        return
    settings = Settings() if arguments.live != "none" else None  # pyright: ignore[reportCallIssue]
    report = await evaluate(judged, settings, arguments.live)
    print_report(report, len(searches))
    if report.failures:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
