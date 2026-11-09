"""Judge Searches: `uv run python -m evals.judge [id ...]`. Each new Search costs a real run."""

import argparse
import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from concert_scout.config import Settings
from evals import cases, harness, snapshots
from evals.cases import Search

SAMPLE = 20
Ask = Callable[[str], str]


@dataclass
class Labels:
    must: list[str] = field(default_factory=list[str])
    good: list[str] = field(default_factory=list[str])
    bad: list[str] = field(default_factory=list[str])


def sample(poster_artists: Sequence[str], names: Sequence[str], size: int = SAMPLE) -> list[str]:
    """The Poster first, because those are the Artists the measures score."""
    return list(dict.fromkeys([*poster_artists, *names]))[:size]


def label_artists(artists: Sequence[str], ask: Ask) -> Labels:
    labels = Labels()
    for index, artist in enumerate(artists, start=1):
        while True:
            answer = ask(
                f"[{index}/{len(artists)}] {artist}: (m)ust (g)ood (b)ad (Enter) neutral? "
            )
            answer = answer.strip().lower()
            if answer in {"m", "must", "g", "good", "b", "bad", "", "n", "neutral"}:
                break
            print("Use m, g, b or Enter for neutral.")
        if answer in {"m", "must"}:
            labels.must.append(artist)
        elif answer in {"g", "good"}:
            labels.good.append(artist)
        elif answer in {"b", "bad"}:
            labels.bad.append(artist)
    # A must Artist the pipeline missed never appears above, so it has to come from the judge.
    others = ask("Other must Artists, comma separated (Enter for none): ")
    labels.must.extend(name.strip() for name in others.split(",") if name.strip())
    return labels


def apply_labels(search: Search, snapshot_id: str, labels: Labels, notes: str) -> Search:
    return search.model_copy(
        update={
            "snapshot": snapshot_id,
            "judged": True,
            "must": labels.must,
            "good": labels.good,
            "bad": labels.bad,
            "notes": notes.strip() or None,
        }
    )


async def judge(
    search: Search, settings: Settings | None, ask: Ask, snapshot: snapshots.Snapshot | None = None
) -> Search:
    print(f"\n{search.id}: {search.text}\nPreparing the Search...")
    if snapshot is None:
        if settings is None:
            raise ValueError("Live capture requires Settings")
        snapshot, result = await harness.capture(search.id, search.text, settings)
        snapshots.save(snapshot)
    else:
        if snapshot.text != search.text:
            raise ValueError("Snapshot text differs from this Search; choose the matching case")
        result, misses = await harness.replay(snapshot, None)
        if misses:
            raise ValueError(
                "Snapshot cannot replay the current pipeline; capture this Search again"
            )
    if result.error:
        print(f"The Search ended with {result.error}.")
    poster_artists = [a.name for r in result.recommendations for a in r.concert.artists]
    print(f"Poster: {', '.join(r.concert.name for r in result.recommendations) or 'empty'}")
    labels = label_artists(sample(poster_artists, result.names), ask)
    return apply_labels(search, snapshot.id, labels, ask("Notes (Enter for none): "))


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ids", nargs="*", help="Search IDs. Default: the next unjudged Search.")
    parser.add_argument(
        "--snapshot", help="Judge one existing Snapshot offline, with no keys or cost."
    )
    arguments = parser.parse_args()
    wanted = arguments.ids
    searches = cases.load()
    chosen = [s for s in searches if s.id in wanted] if wanted else []
    if not wanted:
        chosen = [s for s in searches if not s.judged][:1]
    if not chosen:
        print("Nothing to judge.")
        return
    snapshot = snapshots.load(arguments.snapshot) if arguments.snapshot else None
    if snapshot is not None and len(chosen) != 1:
        parser.error("--snapshot needs exactly one Search ID")
    settings = Settings() if snapshot is None else None  # pyright: ignore[reportCallIssue]
    for search in chosen:
        try:
            judged = await judge(search, settings, input, snapshot)
        except (EOFError, KeyboardInterrupt):
            print("\nReview stopped; this Search was not changed.")
            raise SystemExit(130) from None
        searches = [judged if s.id == judged.id else s for s in searches]
        cases.save(searches)
        print(f"Saved {judged.id}.")


if __name__ == "__main__":
    asyncio.run(main())
