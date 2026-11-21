"""The judged Searches in `evals/searches.yaml`."""

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel

SEARCHES = Path(__file__).parent / "searches.yaml"
REFINEMENTS = Path(__file__).parent / "refinements.yaml"
HEADER = (
    "# Searches for the owner to judge with `uv run python -m evals.judge`. "
    "Labels come only from a person.\n"
)


class Search(BaseModel):
    id: str
    text: str
    snapshot: str | None = None
    must: list[str] = []
    good: list[str] = []
    bad: list[str] = []
    notes: str | None = None
    judged: bool = False


class RefinementCase(BaseModel):
    id: str
    base_search: str
    poster_artists: list[str] = []
    refinement: str
    expect_kind: Literal["refined", "unanswerable"]
    expect_filter_only: bool = False
    expect_weekends_only: bool = False
    expect_place_contains: str | None = None
    expect_adds_artist: str | None = None
    expect_has_max_price: bool = False


def load(path: Path = SEARCHES) -> list[Search]:
    return [Search.model_validate(entry) for entry in yaml.safe_load(path.read_text())]


def load_refinements(path: Path = REFINEMENTS) -> list[RefinementCase]:
    return [RefinementCase.model_validate(entry) for entry in yaml.safe_load(path.read_text())]


def save(searches: list[Search], path: Path = SEARCHES) -> None:
    entries: list[dict[str, Any]] = [
        search.model_dump(exclude_none=True, exclude_defaults=True) for search in searches
    ]
    dumped = yaml.safe_dump(entries, allow_unicode=True, sort_keys=False)
    path.write_text(HEADER + dumped)
