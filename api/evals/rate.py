"""Rate Searches in the browser: `uv run python -m evals.rate [--batch <name>]`.

Each Search replays offline from its Snapshot in the batch, with no keys or cost, and labels are
saved to searches.yaml exactly as `evals.judge` saves them. It listens on this computer only.
"""

import argparse
import webbrowser
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from evals import cases, harness, judge, snapshots
from evals.compare import batch_cases

PORT = 8765
PAGE = Path(__file__).with_name("rate.html")

type Label = Literal["must", "good", "bad", "neutral"]


class Artist(BaseModel):
    name: str
    on_poster: bool
    reason: str | None = None
    label: Label = "neutral"


class Case(BaseModel):
    id: str
    text: str
    judged: bool
    snapshot: str | None


class Detail(Case):
    artists: list[Artist]
    others: list[str]
    notes: str
    error: str | None = None


class Rating(BaseModel):
    labels: dict[str, Label]
    others: list[str] = []
    notes: str = ""


def _latest_batch() -> str:
    reports = sorted(snapshots.SNAPSHOTS.glob("batch-*.json"), key=lambda p: p.stat().st_mtime)
    if not reports:
        raise SystemExit("No batch reports in evals/snapshots. Capture Searches first.")
    return reports[-1].stem


def make_app(batch: str) -> FastAPI:
    captured = batch_cases([batch])
    app = FastAPI(title="Rate Searches")

    def snapshot_for(search: cases.Search) -> str | None:
        return captured.get(search.id) or search.snapshot

    def find(case_id: str) -> cases.Search:
        search = next((s for s in cases.load() if s.id == case_id), None)
        if search is None:
            raise HTTPException(404, "No such Search")
        return search

    @app.get("/", response_class=HTMLResponse)
    async def page() -> str:
        return PAGE.read_text()

    @app.get("/api/searches")
    async def searches() -> list[Case]:
        return [
            Case(id=s.id, text=s.text, judged=s.judged, snapshot=snapshot_for(s))
            for s in cases.load()
        ]

    @app.get("/api/searches/{case_id}")
    async def detail(case_id: str) -> Detail:
        search = find(case_id)
        snapshot_id = snapshot_for(search)
        if snapshot_id is None:
            raise HTTPException(409, "This Search has no Snapshot. Capture it first.")
        snapshot = snapshots.load(snapshot_id)
        result, misses = await harness.replay(snapshot, None)
        if misses:
            raise HTTPException(409, "This Snapshot no longer replays. Capture the Search again.")
        # The reason was written for the bill's first Artist, so the rest only share the bill.
        reasons: dict[str, str] = {}
        for r in result.recommendations:
            names_on_bill = [a.name for a in r.concert.artists] or [r.concert.name]
            reasons.setdefault(names_on_bill[0], r.reason)
            for other in names_on_bill[1:]:
                reasons.setdefault(other, f"On the same bill as {names_on_bill[0]}.")
        names = judge.sample(list(reasons), result.names)
        known: dict[str, Label] = {}
        known |= dict.fromkeys(search.must, "must")
        known |= dict.fromkeys(search.good, "good")
        known |= dict.fromkeys(search.bad, "bad")
        artists = [
            Artist(
                name=n, on_poster=n in reasons, reason=reasons.get(n), label=known.get(n, "neutral")
            )
            for n in names
        ]
        return Detail(
            id=search.id,
            text=search.text,
            judged=search.judged,
            snapshot=snapshot_id,
            artists=artists,
            others=[n for n in search.must if n not in names],
            notes=search.notes or "",
            error=result.error,
        )

    @app.post("/api/searches/{case_id}")
    async def save(case_id: str, rating: Rating) -> Case:
        search = find(case_id)
        snapshot_id = snapshot_for(search)
        if snapshot_id is None:
            raise HTTPException(409, "This Search has no Snapshot.")
        labels = judge.Labels(
            must=[n for n, label in rating.labels.items() if label == "must"],
            good=[n for n, label in rating.labels.items() if label == "good"],
            bad=[n for n, label in rating.labels.items() if label == "bad"],
        )
        labels.must.extend(n.strip() for n in rating.others if n.strip())
        judged = judge.apply_labels(search, snapshot_id, labels, rating.notes)
        cases.save([judged if s.id == judged.id else s for s in cases.load()])
        return Case(id=judged.id, text=judged.text, judged=True, snapshot=snapshot_id)

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", help="batch report name; the newest when left out")
    args = parser.parse_args()
    batch = args.batch or _latest_batch()
    print(f"Rating Searches from {batch} at http://127.0.0.1:{PORT}  (Ctrl+C to stop)")
    webbrowser.open(f"http://127.0.0.1:{PORT}")
    uvicorn.run(make_app(batch), host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
