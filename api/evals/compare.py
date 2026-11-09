"""Compare two eval runs Artist by Artist: `uv run python -m evals.compare --before a --after b`.

It reads what each Snapshot recorded, so runs from different code stay comparable. A Poster count
hides what changed, because stacking dates or a lost Artist can move it by the same amount. No
result here says which run is better. Only human labels can.
"""

import argparse
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from concert_scout.assemble import MIN_LEVEL
from concert_scout.models import Concert
from concert_scout.sources import jev, ticketmaster
from evals import snapshots
from evals.snapshots import Snapshot


@dataclass
class Change:
    id: str
    before: dict[str, int]
    after: dict[str, int]

    @property
    def kept(self) -> set[str]:
        return self.before.keys() & self.after.keys()

    @property
    def overlap(self) -> float:
        everyone = self.before.keys() | self.after.keys()
        return len(self.kept) / len(everyone) if everyone else 1.0


def _concerts(snapshot: Snapshot) -> dict[str, Concert]:
    concerts: dict[str, Concert] = {}
    for key, record in snapshot.records.items():
        if "ticketmaster" in key and record.status == 200:
            for concert in ticketmaster.parse_concerts(json.loads(record.body)):
                concerts[concert.id] = concert
    return concerts


def _levels(snapshot: Snapshot) -> dict[str, int]:
    """Jev's recorded grades, by Concert ID. A Snapshot captured before Jev graded has none."""
    levels: dict[str, int] = {}
    for key, record in snapshot.records.items():
        if snapshots.JEV_HOST in key and record.status == 200:
            levels |= jev.Graded.model_validate_json(record.body).levels()
    return levels


def artists(snapshot: Snapshot) -> dict[str, int]:
    """Each Artist graded onto the Poster, with their level."""
    concerts = _concerts(snapshot)
    scores: dict[str, int] = {}
    for id_, level in _levels(snapshot).items():
        concert = concerts.get(id_)
        if concert and level >= MIN_LEVEL:
            name = concert.artists[0].name if concert.artists else concert.name
            scores[name] = max(scores.get(name, 0), level)
    return scores


def compare(id_: str, before: Snapshot, after: Snapshot) -> Change:
    return Change(id_, artists(before), artists(after))


def report(changes: Iterable[Change]) -> str:
    changes = list(changes)
    lines: list[str] = []
    for change in changes:
        counts = f"{len(change.before)} -> {len(change.after)} Artists"
        lines.append(f"{change.id}: {counts}, {change.overlap:.0%} overlap")
        lost = sorted(change.before.keys() - change.after.keys())
        new = sorted(change.after.keys() - change.before.keys())
        lines += [f"  lost {name} ({change.before[name]})" for name in lost]
        lines += [f"  new  {name} ({change.after[name]})" for name in new]
    before = sum(len(change.before) for change in changes)
    after = sum(len(change.after) for change in changes)
    overlap = sum(change.overlap for change in changes) / max(len(changes), 1)
    lines.append(f"\nAll: {before} -> {after} Artists, {overlap:.0%} mean overlap")
    return "\n".join(lines)


def batch_cases(names: Sequence[str]) -> dict[str, str]:
    """Case ID to Snapshot ID. A later report wins, so a rerun replaces its earlier capture."""
    cases: dict[str, str] = {}
    for name in names:
        body = json.loads((snapshots.SNAPSHOTS / f"{name}.json").read_text())
        cases |= {capture["id"]: capture["snapshot"] for capture in body["captures"]}
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two eval runs Artist by Artist.")
    parser.add_argument("--before", nargs="+", required=True, help="batch report names")
    parser.add_argument("--after", nargs="+", required=True, help="batch report names")
    args = parser.parse_args()
    before, after = batch_cases(args.before), batch_cases(args.after)
    shared = [case for case in before if case in after]
    print(
        report(
            compare(case, snapshots.load(before[case]), snapshots.load(after[case]))
            for case in shared
        )
    )


if __name__ == "__main__":
    main()
