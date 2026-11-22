# Engineering Lab & Ranking Inspector

Concert Scout exposes its runtime behavior, evaluation coverage, and ranking signals publicly without compromising visitor privacy or source-fact integrity. Terms follow [GLOSSARY.md](../../GLOSSARY.md).

## 1. Public Engineering Lab (`/lab` and `GET /lab`)

`GET /lab` returns a `LabSummary` JSON payload with `Cache-Control: public, max-age=30` and renders at `/lab`.

### Anonymized rolling telemetry
- Every completed or interrupted Search records one numeric-only `SearchMetrics` entry into a bounded Redis list (`lab:search_metrics`) using `LPUSH`, `LTRIM 0 199` (latest 200 Searches), and a 7-day `EXPIRE`.
- Recorded fields are strictly numeric plus an hour-bucketed UTC timestamp (`recorded_at`, e.g. `2026-11-22T20:00Z`): `total_ms`, `steps_ms` (allowlisted pipeline step names only), `cost_usd`, `cost_complete`, `cache_hits`, `cache_misses`, `pool_total`, `shortlist_total`, and `picks_total`.
- **Strict privacy invariant**: Telemetry never stores or exposes Search text, Artist names, Reading values, coordinates, IP addresses, usernames, or Spotify data.
- `GET /lab` aggregates `sample_count`, `p50_total_ms`, `p95_total_ms`, `avg_cost_usd` (over `cost_complete` samples), `cache_hit_rate`, average funnel counts, and per-step `p50_ms` / `p95_ms`.
- When Redis has zero samples or is unreachable, `GET /lab` still returns `200` with null numeric aggregates and an honest empty state.

### Eval suite & architecture comparison
- `eval_benchmarks` reads `api/evals/searches.yaml` deterministically at runtime to report real case counts, human-judged counts, snapshot coverage, `must`/`good`/`bad` label totals, category counts, and the quality targets from [06-evals](06-evals.md).
- Three retrieval tiers are compared transparently: `tags-only` (baseline), `co-billing` (shipped, offline-ready), and `hybrid pgvector + Jev` (pending live comparative run after paid-tier embedding backfill per [09-hybrid-retrieval](09-hybrid-retrieval.md)). No benchmark score is ever fabricated.

### Architectural invariants
`/lab` documents the core guarantees enforced by contract tests:
- **ADR 0002**: Concert facts come only from Ticketmaster and JamBase records; unknown ranker IDs are dropped.
- **ADR 0003**: Spotify is reached only via official OAuth on a separate exact-name shelf; Spotify account data never reaches an LLM or Search telemetry.
- **Cost & abuse gates**: Same-origin checks, Turnstile bot verification, hashed per-visitor hourly limits, and daily/monthly spend caps guard every Search.

## 2. Under-the-Hood Ranking Inspector

Each live Search (and cached-session filter-only Refinement) emits an additive `inspect` SSE event immediately before `poster`:
- `reading`: the active Reading.
- `pool_total` and `shortlist_total`: Concert pool size and shortlisted candidate count.
- `steps_ms`: per-step millisecond timings captured during this Search.
- `picks`: one `InspectPick` per Recommendation on the Poster, reporting `concert_id`, `artist`, `concert_name`, primary `signal` (`seed`, `one_hop`, `two_hops`, `co_billed`, `semantic`, `tags`, `genre`), `via` seed, shared `styles`, `match_score`, cumulative `support`, effective `grade`, raw `jev_level`, `lineup_match_count`, and `source`.

On the Poster, a compact **Inspect ranking** toggle sits beside Grid/List/Share only when `inspect` metadata is present. It is closed by default so the Poster and Tickets remain free of numeric scores ([04-interface](04-interface.md)), opens an accessible X-ray panel with smooth reduced-motion-aware transitions, and closes cleanly via its button or `Escape`.

## 3. Zero-Overhead & Failure Isolation

- `lab.record_search` runs inside `run_search`'s shielded `finally` block and catches `RedisError` silently. Telemetry recording can never fail or block a Search.
- `SearchMetrics` forbids extra fields (`extra="forbid"`) and restricts `steps_ms` keys to fixed pipeline step names.
