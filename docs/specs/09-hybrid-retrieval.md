# Hybrid Retrieval: Live Co-Billing Graph & `pgvector`

Streaming similarity (ListenBrainz / Last.fm) suffers from mainstream popularity bias and sparse community tags—especially in electronic, underground club, and regional scenes. This spec adds two grounded live-music signals before Jev grades the top-40 shortlist: a **Live Co-Billing Graph** mined from real Concert Lineups, and **Hybrid `pgvector` Semantic Retrieval** built from source-grounded Sonic Cards and graph-propagated embeddings.

Every Concert fact still comes strictly from its source record ([ADR 0002](../adr/0002-facts-never-pass-through-the-llm.md)).

## 1. Live Co-Billing Graph

Promoters and booking agents curate openers and co-headliners to fit each other's live audience—a signal streaming services do not capture.

### Data model (`supabase/migrations/`)
- Table `public.artist_cobilling`:
  - `artist_a text not null` (normalized name, `artist_a < artist_b` canonical ordering)
  - `artist_b text not null`
  - `weight double precision not null`
  - `shared_shows integer not null default 1`
  - `last_seen date not null`
  - `primary key (artist_a, artist_b)`
  - Indexes on `(artist_a, weight desc)` and `(artist_b, weight desc)` for fast single-hop lookups.
- Table `public.artist_venues` (optional soft scene signal):
  - `(artist_key text, venue_key text, city text, appearances integer, last_seen date)` — tracks recurring appearances at curated small/mid rooms (excluding mega-arenas/stadiums).

### Edge weighting rule (preventing mega-festival pollution)
When ingesting any Concert with `2 <= len(artists) <= 40`:
- Compute bill weight as:
  - `2..5` Artists (club/theater bill): `1.0`
  - `6..15` Artists (mini-fest / showcase): `0.45`
  - `16..40` Artists (mid festival): `0.15`
  - `> 40` Artists (mega multi-genre festival like Coachella): `0.0` (skipped so unrelated headliners never link).
- Accumulate into `artist_cobilling` during daily `/sync` (JamBase national Catalog) and asynchronously on Ticketmaster pool cache writes. Deduplicate by `(concert_id)` via a lightweight seen-bill table or Redis set so re-syncing the same Concert never double-counts an edge.

### Scoring integration (`matching.py`)
- Add `"co_billed"` to `Signal` in `api/concert_scout/matching.py`.
- Pass pre-fetched `cobilling: Mapping[str, Sequence[CoBilledPeer]]` into `Taste` so `matching.py` stays 100% pure and offline-testable.
- Starting weight: `CO_BILLED_WEIGHT = 0.72` (between 1-hop ListenBrainz `0.8` and 2-hop `0.5`, scaled by normalized edge weight, tuned via `api/evals/`).
- Neutral fallback reason: `"Shares bills with {seed}"`.

## 2. Grounded `pgvector` Semantic Retrieval

Plain-text vibe Searches (*"rainy late-night synthwave"*, *"groove-led instrumental"*, *"UK garage"*) fail when local Artists lack exact MusicBrainz tags. Dense semantic vectors bridge descriptors to Artists without letting an LLM invent facts.

### How Artist descriptions ("Sonic Cards") are built
No LLM invents artist bios. Embeddings come from two deterministic tiers:

1. **Tier 1 — Source-Grounded Sonic Card** (Artists with tags, bio, or known peers):
   Structured plain text assembled strictly from public metadata:
   - Artist name + MusicBrainz type / country / disambiguation
   - Cleaned ListenBrainz + MusicBrainz tags (filtered via `usable_tags`) + Ticketmaster/JamBase genre & subgenre
   - Cleaned Last.fm short bio summary (boilerplate/HTML/tour announcements stripped, capped at ~300 chars)
   - Top 10 ListenBrainz/Last.fm similar Artists + top 10 Co-Billed peers
2. **Tier 2 — Graph-Propagated Embedding** (Thin / underground Artists with `< 2` tags and no bio):
   - Compute the weighted centroid vector of their Co-Billed peers' Tier-1 embeddings (normalized to unit length).
   - Zero LLM calls, zero hallucinations, and places unknown openers into the exact sonic neighborhood of the bills they play.

### Storage & Embedding Model
- Enable `pgvector` (`create extension if not exists vector;`) in Supabase.
- Table `public.artist_embeddings`:
  - `artist_key text primary key` (normalized name)
  - `mbid text`
  - `tier smallint not null` (`1` = sonic card, `2` = graph-propagated)
  - `card_hash text not null` (SHA-256 of input Sonic Card so unchanged Artists are never re-embedded)
  - `embedding vector(512) not null` (Matryoshka-truncated 512d `text-embedding-3-small` or `voyage-3-lite` for compact RAM/storage and fast cosine math)
  - `updated_at timestamptz not null default now()`
- Cost: Backfilling 50,000 Catalog Artists at ~80 tokens/card (~4M tokens) costs ~$0.08 one-time; incremental new Artists during daily `/sync` cost <$0.05/month.

### Search-time latency budget (~20–50 ms total added)
1. **Query embedding (0 ms critical path)**: Right after `interpret`, build the Taste query string (`artists`, `descriptors`, `tags`, `genres`) and embed it **in parallel** with `resolve_place`, `find_taste`, and `find_pool`. Cache in Redis for 6 hours (same TTL as `interpret`). Typical ~80 ms call is completely hidden behind the 1–3s pool fetch.
2. **Pool-scoped exact cosine scoring (~20–45 ms)**: Never run a global ANN search and post-filter by city (which drops local acts). Once the Concert pool arrives (typically 150–1,500 unique Artists), run **one** batched Postgres query:
   ```sql
   select artist_key, 1 - (embedding <=> $1::vector) as cosine
   from public.artist_embeddings
   where artist_key = any($2::text[]);
   ```
   Because `artist_key` is the primary key, Postgres looks up only the pool's rows via index and computes exact cosine distance in memory.
3. **Fusion in `matching.py`**:
   - Add `"semantic"` to `Signal` (`SEMANTIC_WEIGHT = 0.65` starting value, thresholded above a calibrated floor e.g. `cosine >= 0.42` so unrelated artists never qualify).
   - Keep `support` summing every signal (`seed`, `one_hop`, `two_hops`, `co_billed`, `semantic`, `tags`, `genre`), so an Artist backed by both semantic similarity and co-billing rises to the top of the 40-candidate shortlist before Jev grades them.

## 3. Research Verdict on Eventbrite & Underground Feeds (Slice 2.4)

Prior live verification (`docs/research/15-eventbrite-authenticated-probe.md`, November 7, 2026) and current Eventbrite API documentation establish:
- Eventbrite permanently shut down global public search (`/v3/events/search/` returns 404).
- `GET /v3/organizers/{id}/events/` works for curated organizer IDs, **but** Eventbrite listings carry **no structured Artist Lineups (`artists=[]`)** and **no genres**, and many titles are unofficial afterparties naming absent Artists. Injecting them into the Artist-matched pool would violate ADR 0002 or drop them silently.
- Underground electronic clubs (Nowadays, Public Records, Elsewhere, Smartbar, Marble Bar, 1015 Folsom) largely publish on Resident Advisor, DICE, or their own calendars with `schema.org/MusicEvent` JSON-LD.

**Decision**: Do **not** block Co-Billing + `pgvector` on Eventbrite. Ship Co-Billing + `pgvector` first against Ticketmaster + JamBase (where structured Lineups already exist and eval lift can be measured immediately). Track a curated `schema.org/MusicEvent` venue harvester + Eventbrite organizer showcase as a separate follow-up slice with explicit non-Lineup event handling.

## 4. Acceptance & Evals

- Run `uv run python -m evals.run` and `uv run python -m evals.scorecard` before and after each slice across all 25 Searches in `api/evals/searches.yaml`.
- Target measurable lift on sparse/electronic Searches (`uk-garage-portland`, `techno-detroit`, `ambient-seattle`, `late-night-rnb-seattle`, `drum-and-bass-boise`) with 0 bad picks added and p95 Search latency increase under 100 ms.
