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
        answer = ask(f"[{index}/{len(artists)}] {artist}: (m)ust (g)ood (b)ad (Enter) neutral? ")
        match answer.strip().lower():
            case "m":
                labels.must.append(artist)
            case "g":
                labels.good.append(artist)
            case "b":
                labels.bad.append(artist)
            case _:
                pass
    # A must Artist the pipeline missed never appears above, so it has to come from the judge.
    others = ask("Other must Artists, comma separated (Enter for none): ")
    labels.must.extend(name.strip() for name in others.split(",") if name.strip())
    return labels


def apply_labels(search: Search, snapshot_id: str, labels: Labels, notes: str) -> Search:
    return search.model_copy(
        update={
            "snapshot": snapshot_id,
            "must": labels.must,
            "good": labels.good,
            "bad": labels.bad,
            "notes": notes.strip() or None,
        }
    )


async def judge(search: Search, settings: Settings, ask: Ask) -> Search:
    print(f"\n{search.id}: {search.text}\nRunning the Search...")
    snapshot, result = await harness.capture(search.id, search.text, settings)
    snapshots.save(snapshot)
    if result.error:
        print(f"The Search ended with {result.error}.")
    poster_artists = [a.name for r in result.recommendations for a in r.concert.artists]
    print(f"Poster: {', '.join(r.concert.name for r in result.recommendations) or 'empty'}")
    labels = label_artists(sample(poster_artists, result.names), ask)
    return apply_labels(search, snapshot.id, labels, ask("Notes (Enter for none): "))


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ids", nargs="*", help="Search IDs. Default: the next unjudged Search.")
    wanted = parser.parse_args().ids
    searches = cases.load()
    chosen = [s for s in searches if s.id in wanted] if wanted else []
    if not wanted:
        chosen = [s for s in searches if not s.judged][:1]
    if not chosen:
        print("Nothing to judge.")
        return
    settings = Settings()  # pyright: ignore[reportCallIssue]
    for search in chosen:
        judged = await judge(search, settings, input)
        searches = [judged if s.id == judged.id else s for s in searches]
        cases.save(searches)
        print(f"Saved {judged.id}.")


if __name__ == "__main__":
    asyncio.run(main())
