# Universal Taste Hub ($0 stack)

Concert Scout should personalize Concerts for every visitor, not only five allowlisted Spotify accounts ([ADR 0003](../adr/0003-official-spotify-access-only.md)). This spec defines the zero-dollar Taste stack that replaces Spotify OAuth as the primary personalization path while keeping official Spotify OAuth strictly isolated for invited testers.

## Goals

- Any visitor can import real Taste in under 20 seconds without Last.fm, ListenBrainz, or a Spotify allowlist slot.
- Signed-in Accounts keep their non-Spotify Taste Profile across devices and see a personalized **For You** shelf on the home page.
- Zero recurring API fees ($0 stack). Paid Apple Music MusicKit JS ($99/yr Apple Developer Program) is deferred until warranted.

## 1. Public YouTube / YouTube Music playlist URL import

Any visitor can paste a public or unlisted YouTube or YouTube Music playlist URL (`youtube.com/playlist?list=...` or `music.youtube.com/playlist?list=...`).

- **API route**: `POST /taste/youtube-playlist` accepting `{url: str}`. Protected by `limit_visitor(request, "taste", limits.TASTE_PER_HOUR)`.
- **Quota safety**: Uses `playlistItems.list` with a server-held `YOUTUBE_API_KEY` (1 quota unit per 50 items out of 10,000 free units/day; never calls `search.list`). Reads at most 4 pages (200 tracks) per import.
- **Artist extraction**:
  1. Prefer `videoOwnerChannelTitle` when it ends with `" - Topic"` (YouTube's auto-generated Artist channels) or `"VEVO"`, stripping the suffix.
  2. Otherwise parse standard `"Artist - Track"` titles (splitting on ` - `, ` – `, ` — `, stripping featured credits and `(Official Video)` / `[Audio]` tags).
  3. Rank extracted Artists by frequency across the playlist, deduplicate by normalized name, and return up to 50 Artists (`ImportedTaste`).
  4. Never log the playlist URL or raw titles; cache normalized playlist results in Redis for 1 hour by hashed playlist ID.
- **UI**: Lives inside the Taste panel alongside Last.fm and ListenBrainz. Shows extracted Artist chips so the visitor can remove stray non-Artist entries before saving.

## 2. Guided Spotify CSV presets & 30-second Taste Seed picker

### Guided CSV import
- Keep client-side parsing in `frontend/lib/taste-files.ts` (raw files never leave the browser).
- Add explicit format detection and tested presets for **Exportify** (`Artist Name(s)` semicolon/comma-separated, ranking by track count) and **TuneMyMusic** CSV/TXT exports.
- In the Taste panel, present a clear two-step helper beside Connect Spotify: *"Not on the invite list? Export a playlist with Exportify or TuneMyMusic and drop the CSV here."*
- **Provenance rule**: Keep Exportify/TuneMyMusic imports labeled clearly as a file import (with import date and "Update import"), never as a live Spotify connection.

### 30-second visual Taste Seed picker
- For visitors with no music account to export, provide a fast interactive picker inside the Taste panel and home guide:
  1. Type and tap 3–5 Artists (with autocomplete backed by MusicBrainz / Catalog Artist names via `GET /artists/suggest?q=`).
  2. After each pick, show 4–6 clickable follow-up chips (*"Also like..."*) drawn from ListenBrainz similarity and the Co-Billing Graph (`GET /artists/related?names=...`) so a visitor can assemble 10–15 Artists in seconds.
  3. Confirming saves the ordered list as their Taste.

## 3. Optional YouTube OAuth (`youtube.readonly`)

- Optional follow-up inside Phase 1 once Google OAuth consent screen verification is submitted (free; supports 100 test users immediately before verification).
- Reads the user's Liked Music (`LL` playlist) and music playlists via `playlistItems.list` (1 unit per 50 items), extracts top 50 Artists, and stores only the confirmed Artist list in the Account's Taste Profile (never raw video history).

## 4. Account-synced Taste Profile & "For You" home shelf

- **Schema (`supabase/migrations/`)**: New table `public.taste_profiles` (`user_id uuid primary key references auth.users(id) on delete cascade`, `source text`, `artists jsonb not null`, `updated_at timestamptz not null default now()`).
  - RLS enabled: `authenticated` may `select` and `delete` own row; only the FastAPI API writes using the secret key (matching [ADR 0004](../adr/0004-optional-accounts-on-supabase.md)).
  - **Strict ADR 0003 boundary**: Spotify OAuth session data NEVER enters `taste_profiles`. Only non-Spotify-OAuth sources (YouTube playlist, Last.fm, ListenBrainz, Taste Seed, pasted list, user-held privacy archive) may sync here.
- **API routes** (all deterministic: no LLM call, no model spend):
  - `GET /account/taste` → the saved Taste Profile (`source`, `artists`, `updated_at`), or `null`.
  - `PUT /account/taste` → replaces it. Takes `{source, artists}` with 1–100 names; a source outside the non-Spotify list is refused (ADR 0003). Names are deduplicated by normalized name, favourites first.
  - `DELETE /account/taste` → clears it.
  - `POST /account/for-you` → body `{near?, time_zone}`. Reads the Account's own Taste Profile server-side, so the browser sends no names. With no `near`, it uses the Alert place; with neither, it answers `for_you_needs_place`.
  - `POST /for-you` → the same shelf for a guest, from `{artists, near, time_zone}`. Nothing is kept.
  - The shelf looks 60 days ahead in the cached local pool. An Artist matches by exact normalized Lineup name, a one-hop similar Artist of the top 5, or a Co-Billing peer of the top 5 (`matching.score_concerts`; genre and tag signals are dropped). Exact names come first, then by score, the Taste's own order and date. At most 3 dates per Artist and 20 Concerts. Each row names its `signal` and the Taste Artist it comes `via`.
- **Sync**: on sign-in the newer of the device's Taste and the Account's Taste Profile wins; afterwards a change or Remove on the device follows to the Account. Deleting the Account deletes the row with it.
- **Home experience**: Any visitor (guest with saved local Taste or signed-in Account with `taste_profiles` + place/Alert place) sees a **"For You near [Place]"** shelf on home—eliminating the Spotify-only cliff.

## Out of scope for $0 stack

- Paid Apple Music MusicKit JS ($99/yr Apple Developer Program) — recorded separately for later if desired.
- Unofficial Spotify scrapers or cookie proxies ([ADR 0003](../adr/0003-official-spotify-access-only.md)).
