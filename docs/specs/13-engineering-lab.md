# Engineering Lab & Ranking Inspector

Concert Scout exposes its runtime behavior, evaluation coverage, and ranking signals publicly without compromising visitor privacy or source-fact integrity. Terms follow [GLOSSARY.md](../../GLOSSARY.md).

## 1. Public Engineering Lab (`/lab` and `GET /lab`)

`GET /lab` returns a `LabSummary` JSON payload with `Cache-Control: public, max-age=30` and renders at `/lab`.

### Permanent anonymized telemetry
- Every completed or interrupted Search records one strictly numeric `SearchMetrics` row into `public.search_telemetry` (`supabase/migrations/20261122020000_search_telemetry.sql`) so historical production Searches accumulate permanently without expiring.
- Recorded fields are strictly numeric plus an hour-bucketed UTC timestamp (`recorded_at`, e.g. `2026-11-22T20:00Z`): `total_ms`, `steps_ms` (allowlisted pipeline step names only), `cost_usd`, `cost_complete`, `cache_hits`, `cache_misses`, `pool_total`, `shortlist_total`, and `picks_total`.
- **Strict privacy invariant**: Telemetry never stores or exposes Search text, Artist names, Reading values, coordinates, IP addresses, usernames, or Spotify data.
- `GET /lab` aggregates up to the latest 2,000 Postgres rows alongside exact `all_time_count` (cached in Redis for 30s) and falls back cleanly to a 200-Search Redis ring buffer when Supabase is unconfigured.
- An anonymized cold-capture baseline (`api/evals/baseline_timings.json`, measured from 158 unwarmed snapshots) sits alongside live metrics, and `api/scripts/backfill_lab_telemetry.py` can backfill historical `search span=...` log lines into `public.search_telemetry`.

### Eval suite & architecture comparison
- `eval_benchmarks` reads `api/evals/searches.yaml` deterministically at runtime to report real case counts, human-judged counts, snapshot coverage, `must`/`good`/`bad` label totals, category counts, and quality targets from [06-evals](06-evals.md).
- Three retrieval tiers are compared transparently: `tags-only` (baseline), `co-billing` (shipped, offline-ready), and `hybrid pgvector + Jev` (pending live comparative run after paid-tier embedding backfill per [09-hybrid-retrieval](09-hybrid-retrieval.md)). No benchmark score is ever fabricated.

## 2. Under-the-Hood Ranking Inspector (Opt-in)

Each live Search (and cached-session filter-only Refinement) emits an additive `inspect` SSE event immediately before `poster` containing `reading`, `pool_total`, `shortlist_total`, `steps_ms`, and per-pick signals/grades (`InspectPick`).

- **Clean default Posters**: Everyday visitors never see an "Inspect ranking" button on Posters or a developer toggle in the header menu.
- **Inspect inside `/lab`**: Opening `/lab` automatically renders the Ranking Inspector for the latest Search kept in that browser tab.
- **Opt-in inline toggle**: `/lab` includes a browser-local switch (`Show Inspect button on Posters`) that unlocks the compact **Inspect ranking** drawer beside Grid/List/Share on Posters (also unlockable via `?inspect=1`).

## 3. Zero-Overhead & Failure Isolation

- `lab.record_search` runs inside `run_search`'s shielded `finally` block and catches database/Redis errors silently so telemetry can never fail or block a Search.
- `SearchMetrics` forbids extra fields (`extra="forbid"`) and restricts `steps_ms` keys to fixed pipeline step names.
