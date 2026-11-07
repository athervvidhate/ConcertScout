"""Repeat each captured Search and score every Poster it gets:
`uv run python -m evals.scorecard --batch <name> [--runs 5] [--live none|all] [case ...]`.

Sources replay from each Snapshot. By default only the ranker is called live, so every run sees
the same shortlist and only the ranker can differ. `--live all` also reads the Search afresh,
which is what a visitor sees. Both cost money. `--live none` calls no model and scores only the
shortlist, so a matching change can be measured for the price of grading new Artists.

Measures, none of which needs a human label:
- overlap: how alike repeated Posters are. The same input should get the same answer.
- silver recall: for a Search that names an Artist, how many of the Artists Deezer or Last.fm
  call similar and who are playing reach the Poster. See `evals.silver`.
- graded precision and recall: what share of the Poster a stronger model grades a fair fit or
  better, and how many of the shortlist's strong fits made it. See `evals.grade`.
- shortlist silver and graded share: the same two checks on what the ranker was given.
- pool strong fits kept: with `--pool`, the strong fits among everyone playing that reached the
  shortlist. A Search whose pool holds none has nothing for matching to find.

Seeds always lead the Poster, so they count in none of the quality measures.
"""

import argparse
import asyncio
import math
import statistics
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from itertools import combinations

from concert_scout import cache, limits, pipeline, ranker, telemetry
from concert_scout.config import Settings
from concert_scout.models import Recommendation
from concert_scout.names import normalize
from evals import cases, harness, jev, snapshots
from evals.compare import batch_cases
from evals.grade import GOOD, Grader, Row, agreement
from evals.silver import Silver, recall
from evals.snapshots import Live

# Live runs of one Search at once, so a batch stays well inside the model's rate limits.
CONCURRENT_RUNS = 4
STRONG = 3


@dataclass
class Card:
    id: str
    posters: list[frozenset[str]]
    shortlists: int
    failures: int
    seeds: frozenset[str] = frozenset()
    silver: set[str] = field(default_factory=set[str])
    levels: dict[str, int] = field(default_factory=dict[str, int])
    shortlisted: set[str] = field(default_factory=set[str])
    playing: set[str] = field(default_factory=set[str])
    # Seconds the ranker took in each run, its votes included.
    seconds: list[float] = field(default_factory=list[float])
    # How often the grader sided with the owner's labels, when there are any.
    agreement: float | None = None
    cost: Decimal = Decimal(0)

    @property
    def overlap(self) -> float:
        return mean_overlap(self.posters)

    def sometimes(self) -> list[tuple[str, int]]:
        counts = Counter(name for poster in self.posters for name in poster)
        flaky = [(name, n) for name, n in counts.items() if n < len(self.posters)]
        return sorted(flaky, key=lambda item: (-item[1], item[0]))

    def silver_recall(self) -> float | None:
        """Out of every silver Artist playing, so a candidate the pipeline missed counts too."""
        playing = self.silver & self.playing
        return _mean([recall(set(p - self.seeds), playing, len(self.seeds)) for p in self.posters])

    def shortlist_silver(self) -> float | None:
        """Silver Artists playing that the shortlist kept. Only matching decides this."""
        playing = (self.silver & self.playing) - self.seeds
        return len(playing & self.shortlisted) / len(playing) if playing else None

    def shortlist_strong(self) -> float | None:
        """Strong fits in the whole pool that the shortlist kept. Needs `--pool`."""
        strong = {n for n in self.playing if self.levels.get(n, 0) >= STRONG} - self.seeds
        return len(strong & self.shortlisted) / len(strong) if strong else None

    def shortlist_graded(self) -> float | None:
        """The shortlist's share graded a fair fit or better: what the ranker had to work with."""
        graded = [self.levels[n] for n in self.shortlisted - self.seeds if n in self.levels]
        return sum(level >= GOOD for level in graded) / len(graded) if graded else None

    def graded_precision(self) -> float | None:
        def share(poster: frozenset[str]) -> float | None:
            graded = [self.levels[n] for n in poster - self.seeds if n in self.levels]
            return sum(level >= GOOD for level in graded) / len(graded) if graded else None

        return _mean([share(p) for p in self.posters])

    def graded_recall(self) -> float | None:
        strong = {n for n, level in self.levels.items() if level >= STRONG} - self.seeds
        return _mean([recall(set(p), strong, len(self.seeds)) for p in self.posters])


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Shared Artists as a share of everyone on either Poster. Two empty Posters agree."""
    union = a | b
    return len(a & b) / len(union) if union else 1.0


def mean_overlap(posters: Sequence[frozenset[str]]) -> float:
    pairs = [jaccard(a, b) for a, b in combinations(posters, 2)]
    return statistics.mean(pairs) if pairs else 1.0


def _mean(values: Sequence[float | None]) -> float | None:
    known = [v for v in values if v is not None]
    return statistics.mean(known) if known else None


def poster_artists(recommendations: Sequence[Recommendation]) -> frozenset[str]:
    """Each Poster entry's headliner by normalized name, the Artist the visitor reads first."""
    return frozenset(
        normalize(r.concert.artists[0].name if r.concert.artists else r.concert.name)
        for r in recommendations
    )


async def repeat(
    case_id: str, snapshot: snapshots.Snapshot, runs: int, live: Live, settings: Settings
) -> tuple[Card, list[str]]:
    slots = asyncio.Semaphore(CONCURRENT_RUNS)

    async def once() -> tuple[harness.SearchRun, list[str]]:
        async with slots:
            return await harness.replay(snapshot, settings, live)

    replays = await asyncio.gather(*(once() for _ in range(runs)))
    # A live interpreter can read the Search differently and ask for a source call the Snapshot
    # never saw, so that run has no fair Poster. Otherwise the reading is recorded, and a miss
    # comes from a ranker with no answer or from the search elsewhere after an empty Poster.
    finished = [
        r
        for r, misses in replays
        if r.error is None and r.seconds_to_poster is not None and (live != "all" or not misses)
    ]
    shortlist = list(dict.fromkeys(name for r in finished for name in r.names))
    # A Poster can name a Lineup's headliner where the shortlist named the matched Artist.
    headliners = (
        r.concert.artists[0].name if r.concert.artists else r.concert.name
        for run in finished
        for r in run.recommendations
    )
    shown = list(dict.fromkeys([*shortlist, *headliners]))
    card = Card(
        id=case_id,
        # With no model the Poster is the fallback, which says nothing about the ranker.
        posters=[] if live == "none" else [poster_artists(r.recommendations) for r in finished],
        # A different shortlist means the interpreter read the Search differently.
        shortlists=len({tuple(r.names) for r in finished}),
        failures=len(replays) - len(finished),
        shortlisted={normalize(name) for name in shortlist},
        seconds=[r.steps["rank"] for r in finished if "rank" in r.steps],
        cost=sum((r.cost for r, _ in replays), Decimal(0)),
    )
    return card, shown


async def score(
    card: Card,
    snapshot: snapshots.Snapshot,
    names: list[str],
    silver: Silver,
    grader: Grader,
    pool: bool,
) -> None:
    reading = snapshots.interpretation(snapshot)
    seeds = reading.artists if reading else []
    card.seeds = frozenset(normalize(seed) for seed in seeds)
    if seeds:
        card.silver = await silver.neighbours(seeds)
    lineups = [a for concert in snapshots.source_concerts(snapshot) for a in concert.artists]
    card.playing = {normalize(artist.name) for artist in lineups}
    genres = {normalize(artist.name): artist.subgenre or artist.genre for artist in lineups}
    if pool:
        names = list(dict.fromkeys([*names, *(artist.name for artist in lineups)]))
    rows = [Row(artist=name, genre=genres.get(normalize(name))) for name in names]
    with telemetry.search() as usage:
        card.levels = await grader.grade(snapshot.text, rows) if rows else {}
    card.cost += usage.cost


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{value:.0%}"


def lines(card: Card) -> list[str]:
    sizes = ", ".join(str(len(p)) for p in card.posters)
    head = (
        f"{card.id}: overlap {card.overlap:.0%}, silver recall {_percent(card.silver_recall())}, "
        f"graded precision {_percent(card.graded_precision())}, "
        f"graded recall {_percent(card.graded_recall())}, "
        f"grader agrees with labels {_percent(card.agreement)}"
    )
    candidates = (
        f"  shortlist: silver {_percent(card.shortlist_silver())}, "
        f"graded fair or better {_percent(card.shortlist_graded())}, "
        f"pool strong fits kept {_percent(card.shortlist_strong())}"
    )
    detail = (
        f"  Artists per run {sizes}; {card.shortlists} shortlist(s), {card.failures} failed; "
        f"silver {len(card.silver & card.playing)} playing, "
        f"{len(card.silver & card.shortlisted)} shortlisted"
    )
    flaky = [
        f"  {n}/{len(card.posters)}  {name} (grade {card.levels.get(name, '?')})"
        for name, n in card.sometimes()
    ]
    if not card.posters:
        return [card.id + candidates.removeprefix(" ")]
    return [head, candidates, detail, *flaky]


def summary(cards: Sequence[Card]) -> str:
    def mean(values: Sequence[float | None]) -> str:
        return _percent(_mean(values))

    overlaps = [card.overlap for card in cards]
    cost = sum((card.cost for card in cards), Decimal(0))
    seconds = sorted(s for card in cards for s in card.seconds)
    slowest = seconds[math.ceil(len(seconds) * 0.95) - 1] if seconds else 0.0
    return (
        f"Overlap {mean(overlaps)} (lowest {min(overlaps):.0%}), "
        f"silver recall {mean([c.silver_recall() for c in cards])}, "
        f"graded precision {mean([c.graded_precision() for c in cards])}, "
        f"graded recall {mean([c.graded_recall() for c in cards])}; "
        f"shortlist silver {mean([c.shortlist_silver() for c in cards])}, "
        f"shortlist graded {mean([c.shortlist_graded() for c in cards])}, "
        f"pool strong kept {mean([c.shortlist_strong() for c in cards])}; "
        f"grader agrees {mean([c.agreement for c in cards])}; "
        f"ranker seconds median {statistics.median(seconds or [0]):.1f} p95 {slowest:.1f}, "
        f"cost ${cost:.4f}"
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", nargs="+", required=True, help="batch report names")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--live", choices=["none", "ranker", "all"], default="ranker")
    parser.add_argument(
        "--pool", action="store_true", help="also grade every Artist playing; costs more once"
    )
    parser.add_argument("--votes", type=int, default=ranker.VOTES, help="ranker votes to try")
    parser.add_argument(
        "--ranker",
        choices=["haiku", "jev", "jev-reasons"],
        default="haiku",
        help="jev grades with Jev; jev-reasons adds Haiku reasons for the keepers",
    )
    parser.add_argument("cases", nargs="*", help="case IDs; all in the batch when left out")
    args = parser.parse_args()
    settings = Settings()  # pyright: ignore[reportCallIssue]
    ranker.VOTES = args.votes
    if args.ranker != "haiku":
        reasons = "haiku" if args.ranker == "jev-reasons" else "none"
        pipeline.rank = jev.make(reasons, harness.real_model(settings))
    labels = {search.id: search for search in cases.load() if search.judged}
    chosen = batch_cases(args.batch)
    if args.cases:
        chosen = {case: chosen[case] for case in args.cases}
    lastfm_key = settings.lastfm_key.get_secret_value() if settings.lastfm_key else None
    silver = Silver(lastfm_key)
    grader = Grader(settings.anthropic_api_key.get_secret_value())
    cards: list[Card] = []
    try:
        async with cache.make_client(settings.redis_url) as ledger:
            for case, snapshot_id in chosen.items():
                await limits.check_spend(ledger, limits.EVAL_DAILY_SPEND)
                snapshot = snapshots.load(snapshot_id)
                runs = 1 if args.live == "none" else args.runs
                card, names = await repeat(case, snapshot, runs, args.live, settings)
                await score(card, snapshot, names, silver, grader, args.pool)
                if judged := labels.get(case):
                    card.agreement = agreement(
                        card.levels, [*judged.must, *judged.good], judged.bad
                    )
                await limits.record_spend(ledger, card.cost)
                cards.append(card)
                print("\n".join(lines(card)), flush=True)
    finally:
        await silver.aclose()
        grader.save()
    if cards:
        print("\n" + summary(cards))
    if args.ranker != "haiku":
        print(jev.report())


if __name__ == "__main__":
    asyncio.run(main())
