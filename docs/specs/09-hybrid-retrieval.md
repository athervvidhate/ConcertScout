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

1. **Tier 1 — Source-Grounded Sonic Card** (Artists with at least 2 usable tags or a bio):
   Structured plain text assembled strictly from public metadata, in a fixed order so the same facts always give the same text:
   - Artist name + MusicBrainz type and country, as ListenBrainz relays them
   - Cleaned ListenBrainz/MusicBrainz and Last.fm tags (filtered via `usable_tags`, strongest first, at most 8) + the Ticketmaster/JamBase genre and subgenre
   - Cleaned Last.fm summary (markup, links, tour and ticket notices and "there are N artists with this name" boilerplate stripped, capped at 300 chars)
   - Top 10 similar Artists (ListenBrainz when the Artist has a MusicBrainz ID, else Last.fm) + top 10 Co-Billed peers
2. **Tier 2 — Graph-Propagated Embedding** (Thin / underground Artists with `< 2` tags and no bio):
   - Compute the weighted centroid vector of their Co-Billed peers' Tier-1 embeddings (weight = accumulated bill weight, normalized to unit length). Only Tier-1 vectors count, so a centroid never averages other centroids.
   - An Artist whose peers have no Tier-1 vector yet gets no row, and the next run tries again.
   - Zero LLM calls, zero hallucinations, and places unknown openers into the exact sonic neighborhood of the bills they play.

### Storage & Embedding Model
- Enable `pgvector` (`create extension if not exists vector;`) in Supabase.
- Table `public.artist_embeddings`:
  - `artist_key text primary key` (normalized name)
  - `mbid text`
  - `tier smallint not null` (`1` = sonic card, `2` = graph-propagated)
  - `card_hash text not null` (SHA-256 of the Sonic Card for Tier 1, or of each peer, its weight and its card hash for Tier 2, so unchanged Artists are never re-embedded)
  - `embedding vector(512) not null` (unit length)
  - `updated_at timestamptz not null default now()`
- Embedding model: Google `gemini-embedding-001` through Pydantic AI's `Embedder`, truncated to 512 dimensions with the `dimensions` setting. Cards use the `RETRIEVAL_DOCUMENT` task type and Search queries `RETRIEVAL_QUERY`. Gemini normalizes only its full 3,072 dimensions, so code scales every vector to unit length before storing or averaging it.
- The key is `GOOGLE_API_KEY`, a Gemini API (AI Studio) key. The client is built on the API-key path explicitly, so `GOOGLE_GENAI_USE_VERTEXAI` in the environment never moves it to Vertex. The key also needs `SUPABASE_URL` and `SUPABASE_SECRET_KEY`. With any of them unset, semantic retrieval is off and Search behaves exactly as it does without this slice. Use a paid-tier key in production: the free tier is capped at 100 embedding requests a minute (each text in a batch counts) and Google may use its requests to improve its products.
- Cost: the paid rate is $0.15 per million input tokens and the API reports no usage, so code records an estimate (4 characters a token) against the Search's spend. A Sonic Card is about 20 to 80 tokens, so backfilling 50,000 Catalog Artists costs about $0.15 to $0.60 once. Incremental new Artists during the daily `/sync` cost cents a month.
- Operations:
  - `uv run python scripts/embed_artists.py` backfills every Artist in the Catalog. It skips unchanged cards, so a repeat run costs nothing. `--only-new`, `--limit` and `--artist` narrow it.
  - `/sync` embeds up to 300 new Artists playing in the next month in busy cities, in the 30 seconds after the MusicBrainz step. A failed provider only ends that step.

### Search-time latency budget (~20–50 ms total added)
1. **Query embedding (0 ms critical path)**: Right after the Reading, build the Taste query string (`artists`, `descriptors`, `tags`, `genres`, never the place or dates) and embed it **in parallel** with `resolve_place`, `find_taste`, and `find_pool`. Cache in Redis for 6 hours under a hashed key (same TTL as `interpret`). A Search waits at most 5 seconds for it. Typical ~80 ms call is completely hidden behind the 1–3s pool fetch.
2. **Pool-scoped exact cosine scoring (~20–45 ms)**: Never run a global ANN search and post-filter by city (which drops local acts). Once the Concert pool arrives (typically 150–1,500 unique Artists), run **one** batched Postgres query:
   ```sql
   select artist_key, 1 - (embedding <=> $1::vector) as cosine
   from public.artist_embeddings
   where artist_key = any($2::text[]);
   ```
   The `semantic_scores` function in the migration does exactly this and also drops rows under the floor, so its answer stays inside the Data API's 1,000-row limit. Because `artist_key` is the primary key, Postgres looks up only the pool's rows via index and computes exact cosine distance in memory. A Search waits at most 2 seconds for it. An Artist with no vector is simply absent.
3. **Fusion in `matching.py`**:
   - Add `"semantic"` to `Signal`. `Taste.semantic` holds the pre-fetched cosine by normalized Artist name, so `matching.py` stays pure. An Artist at or above `SEMANTIC_FLOOR` scores `SEMANTIC_WEIGHT * (cosine - floor) / (1 - floor)`, with `SEMANTIC_WEIGHT = 0.65`, so the floor scores 0 and an identical vector scores the full weight. The floor is `0.65`, provisional: on November 20, 2026 `gemini-embedding-001` at 512 dimensions put an unrelated Artist's card near 0.58 and a fitting one near 0.70 for a "uk garage" query, so the 0.42 this spec first guessed would admit everyone. Tune it, and the weight, against the evals below. The neutral reason is "{Artist} sounds close to your Search", and a festival Lineup entry is named only when its score reaches `LINEUP_TAG_SCORE`.
   - Keep `support` summing every signal (`seed`, `one_hop`, `two_hops`, `co_billed`, `semantic`, `tags`, `genre`), so an Artist backed by both semantic similarity and co-billing rises to the top of the 40-candidate shortlist before Jev grades them.

## 3. Research Verdict on Eventbrite & Underground Feeds (Slice 2.4)

Prior live verification (`docs/research/15-eventbrite-authenticated-probe.md`, November 7, 2026) and current Eventbrite API documentation establish:
- Eventbrite permanently shut down global public search (`/v3/events/search/` returns 404).
- `GET /v3/organizers/{id}/events/` works for curated organizer IDs, **but** Eventbrite listings carry **no structured Artist Lineups (`artists=[]`)** and **no genres**, and many titles are unofficial afterparties naming absent Artists. Injecting them into the Artist-matched pool would violate ADR 0002 or drop them silently.
- Underground electronic clubs (Nowadays, Public Records, Elsewhere, Smartbar, Marble Bar, 1015 Folsom) largely publish on Resident Advisor, DICE, or their own calendars with `schema.org/MusicEvent` JSON-LD.

**Decision**: Do **not** block Co-Billing + `pgvector` on Eventbrite. Ship Co-Billing + `pgvector` first against Ticketmaster + JamBase (where structured Lineups already exist and eval lift can be measured immediately). Track a curated `schema.org/MusicEvent` venue harvester + Eventbrite organizer showcase as a separate follow-up slice with explicit non-Lineup event handling.

## 4. Acceptance & Evals

Status on November 20, 2026: the code, migration, backfill and fallbacks are in, and the 0.65 floor above rests on two probe pairs. The before/after run is still to do. The development key sits on Gemini's free tier, which stops at 1,000 embedding requests a day (each text counts), and a day's quota went on the first captures. The recorded Snapshots need an offline vector for every Artist in each pool, so the run needs either that quota to reset or a paid-tier key. Snapshots replay with no Supabase or Google key, so `evals.run` and `evals.scorecard` as they stand measure matching without this signal.

- Run `uv run python -m evals.run` and `uv run python -m evals.scorecard` before and after each slice across all 25 Searches in `api/evals/searches.yaml`.
- Target measurable lift on sparse/electronic Searches (`uk-garage-portland`, `techno-detroit`, `ambient-seattle`, `late-night-rnb-seattle`, `drum-and-bass-boise`) with 0 bad picks added and p95 Search latency increase under 100 ms.
