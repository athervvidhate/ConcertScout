# Real eval capture and offline replay — November 6, 2026

Issue #22 now supports advance capture and offline human judging. All 20 drafted Searches were captured against real configured providers, then replayed through the actual pipeline with socket connections forbidden. No relevance labels were supplied.

- Captured/replayed: **20/20**, no pipeline errors or missing requests.
- Assembled Posters: **zero changed source facts or unknown source IDs** across all replays. Unknown ranker IDs are dropped before assembly; replay logs exercised that guard twice.
- Measured total model cost: **$0.0200599**; mean **$0.001002995** per Search. All usage costs complete and recorded in the shared spend ledger.
- Median time to Poster: **12.7s**; p95: **18.1s**. The under15s p95 target is **missed**. These are fresh-cache live-source captures from this Mac, not remote hosting cold starts.
- Known configured keys were absent from every saved Snapshot; all Snapshot files had mode0600. Raw source/model responses stay gitignored and are not part of this report.
- Human judgments: **0/20**. Bad-pick rate, must-find recall and judged-good share are not yet measured.

| Search | Picks | Candidates | Seconds to Poster | Cost USD |
|---|---:|---:|---:|---:|
| tyler-childers-chicago | 8 | 48 | 18.09 | 0.0013847 |
| turnstile-new-york | 8 | 52 | 16.36 | 0.0014465 |
| four-tet-london | 8 | 46 | 19.16 | 0.0009619 |
| khruangbin-chicago | 8 | 52 | 13.30 | 0.0010454 |
| dreamy-guitar-seattle | 6 | 51 | 9.08 | 0.0011686 |
| shoegaze-portland | 1 | 26 | 5.16 | 0.0005958 |
| techno-detroit | 4 | 53 | 12.67 | 0.0010960 |
| boise-country | 5 | 56 | 16.48 | 0.0010557 |
| no-place-turnstile | 8 | 3 | 14.09 | 0.0009921 |
| new-york-jazz | 8 | 15 | 15.77 | 0.0012977 |
| chicago-far-month | 0 | 4 | 4.12 | 0.0004287 |
| boise-shoegaze | 4 | 57 | 9.85 | 0.0012035 |
| ambient-seattle | 5 | 59 | 10.68 | 0.0011392 |
| punk-los-angeles | 7 | 46 | 17.49 | 0.0010021 |
| folk-austin | 8 | 54 | 9.48 | 0.0009268 |
| four-tet-boise | 2 | 7 | 8.88 | 0.0006253 |
| instrumental-san-francisco | 8 | 56 | 10.67 | 0.0009813 |
| metal-denver | 8 | 48 | 12.74 | 0.0011553 |
| no-place-khruangbin | 8 | 3 | 14.26 | 0.0010226 |
| sparse-answer | 0 | 7 | 5.17 | 0.0005307 |

## Verification

`make check` passed: lint/types, **133 backend contracts** and **19 frontend data tests**. The seven additional eval contracts cover echoed-key redaction, private/non-overwriting evidence, all-neutral reviews and invalid input, restored pacing, offline/mismatched-text judging, paid failure accounting/cleanup and pipeline failures rather than silent quality scores. The existing18 production browser checks passed in the preceding hosting change; this change only touches eval tooling and documentation. CI runs the full browser suite again.

The real offline judge command reached its first human prompt and a clean cancellation using the Tyler Childers capture; the Search YAML hash stayed unchanged. `evals.run` correctly reports no judged Searches. A person must complete the labels before quality scores mean anything.

```sh
cd api
uv run python -m evals.judge tyler-childers-chicago --snapshot tyler-childers-chicago-2026-11-06-6e288447
```

That ID is local evidence on the current worktree. The private batch reports are `api/evals/snapshots/batch-2026-11-06-100007-a2ec852d.json` and `batch-2026-11-06-100112-1c4c18ad.json`. Other machines must capture their own source data. [Workflow](../development/evals.md).

Issue #22 stays open for owner judging and acceptance of the few-minutes workflow. No human labels were fabricated; no weights or quality thresholds were tuned from unjudged data.
