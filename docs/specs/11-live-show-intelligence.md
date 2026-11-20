# Live-Show Intelligence (Pre-Show Dossier)

Studio streams do not tell a person what being in the room actually feels like. This spec upgrades the Ticket dialog and Artist panel with three strictly source-grounded signals—**Recent Setlist DNA**, **Watch Live** (official peak-moment live clip), and **Venue Room Character + Venue Following**—fetched lazily on demand so Search latency stays untouched.

Every fact comes from its source record ([ADR 0002](../adr/0002-facts-never-pass-through-the-llm.md)). Missing data stays omitted.

## 1. Recent Setlist DNA (Setlist.fm)

- **Source**: Official Setlist.fm REST API (`SETLISTFM_API_KEY`, free for non-commercial projects, `Accept: application/json`, `User-Agent` per repo rules). Respect ~2 req/s via a shared Redis rate gate (`limits.py`).
- **Lookup**: Lazy only—called when a person opens a Ticket's **Live Show** / **Setlist** pane or the Artist panel, never during `/search`.
- **Keying & Cache**: Query by MusicBrainz ID (`/rest/1.0/artist/{mbid}/setlists?p=1`), falling back to exact normalized name only when no MBID exists. Cache parsed summary in Redis for **7 days**.
- **What is computed in code (zero LLM)**:
  - Last 5 completed setlists (with at least 3 songs recorded).
  - `average_songs`: rounded median/mean song count across those shows.
  - `last_show`: `{date, venue, city}` from the most recent recorded setlist.
  - `staples`: top 6–8 songs sorted by appearance count across the last 5 shows (e.g., *"Played in 5 of last 5 shows"*), plus encore frequency when present.
  - `source_url`: direct link to the Artist's Setlist.fm page (attribution required by Setlist.fm terms).
- **API route**: `GET /artist/setlist?name=...&mbid=...` (visitor-rate-limited like `/artist`).

## 2. "Watch Live": Curated Live-Session Index & Official Peak-Moment Clip

Hearing a studio Spotify track is great; watching 45 seconds of the Artist's best live moment sells the Ticket.

### Why we do NOT scrape YouTube's "Most Replayed" heatmap
YouTube Data API v3 does not expose `intensityScoreNormalized` heatmap curves. Scraping watch pages or internal Innertube responses is brittle and violates YouTube terms. Instead, we deliver the same peak-moment jump using **100% official YouTube Data API v3 endpoints**:

### Step A — Zero-Quota Curated Live-Session Index
Because `search.list` costs 100 quota units (max 100/day free), we **do not** rely on `search.list` for every Artist:
- A weekly cron (`GET /sync-live-clips`, protected by `CRON_SECRET`) syncs the official public uploads playlist of each premier high-production live channel via `playlistItems.list` (**1 unit per 50 videos**, the newest 1,500 uploads of each, so 210 units a week at most). A channel's uploads playlist is its channel ID with `UC` changed to `UU`, which keeps the sync free of playlist IDs that can move. A title pattern per channel keeps the live sessions and drops its other uploads:
  - NPR Tiny Desk Concerts
  - KEXP Live Performances
  - Boiler Room Sets
  - Cercle
  - COLORS
  - Audiotree Live
  - BBC Radio 1 Live Lounge
- Index entries expire after 14 days under `live:index:{artist_key}`, kept in the order of the list above, which is the order a Ticket's clip is chosen from. Where an Artist has a whole-set video and single songs in one channel, the whole set is kept.
- Parse Artist name from each video's structured title pattern (e.g., `"Khruangbin: Tiny Desk Concert"`, `"Fred again.. | Boiler Room: London"`) and index `artist_key -> [{video_id, title, session}]` in Redis.
- Fallback: When an Artist is not in the curated index and a visitor explicitly clicks **Watch Live**, run one bounded `search.list` query (`"{artist} live performance"`, `videoEmbeddable=true`, `videoCategoryId=10`, strict daily cap of 60 calls/day in Redis) and cache the result for **30 days** (including negative misses for 14 days).

### Step B — Official Peak-Moment Start Time (`?start=<seconds>`)
For the chosen `video_id`, determine the best start timestamp using two 1-unit official calls (cached 30 days):
1. **Chapter / Description Tracklist Match** (`videos.list`, `part=snippet,contentDetails`): Parse standard `MM:SS` / `H:MM:SS` chapter lines in `snippet.description`. If a track name matches one of the Artist's top Last.fm tracks or Setlist.fm staples, jump straight to that timestamp.
2. **Crowd-Sourced Top Comment Timestamp** (`commentThreads.list`, `order=relevance`, `maxResults=15`): Scan the highest-liked comments for a clear `MM:SS` / `H:MM:SS` timestamp within `[15s, duration - 30s]` (filtering out spam/bot comments). The most-liked timestamp comment on live concert videos almost always marks the peak drop, solo, or crowd moment—giving a legal, official equivalent to "Most Replayed".
3. **Clean Fallback**: If the video is a full set (`duration > 10m`) with neither chapters nor timestamped comments, start at `min(180s, 20% of duration)` to skip tuning/intros; if a single-song live clip (`<= 10m`), start at `0`.

### Ticket UI Integration
- Inside the fixed-height Ticket media column (preserving [04-interface.md](04-interface.md)), offer a clean switch when available: **Photo** · **Listen** (Spotify Preview) · **Watch Live** (official `youtube-nocookie.com/embed/{video_id}?start={seconds}&rel=0`).
- Lazy-load YouTube only after the visitor presses **Watch Live** (zero YouTube cookies or network requests before click; document in `/privacy`).
- Keep focus on the toggle button (same Escape-key safeguard as Spotify's embed) and never overlay custom chrome over the YouTube player.

## 3. Room Character & Followed Venues

### Venue Room Character
- Lazy enrichment route `GET /venue?name=...&city=...` (cached 60 days in Redis):
  - Match venue against **MusicBrainz Places** and **Wikidata** (`P1083` maximum capacity, `P31` venue type, coordinates proximity check within 1 km to avoid false namesake matches).
  - Derive a clean factual tier strictly from verified capacity:
    - `<= 500`: `Intimate club`
    - `501–1,500`: `Club / Ballroom`
    - `1,501–5,000`: `Theater`
    - `5,001–15,000`: `Amphitheater / Large hall`
    - `> 15,000`: `Arena / Stadium`
  - Show on Ticket beside the venue name (e.g., `Bowery Ballroom · Intimate club · 575 cap`). If unverified, show only the venue name.
  - Also backfill known venue capacities for recurring venues in the Catalog so Poster Sculpting's `Intimate rooms` filter works without extra runtime calls.

### Followed Venues (`supabase/migrations/` & Alerts)
- New table `public.followed_venues`:
  - `user_id uuid not null references auth.users(id) on delete cascade`
  - `venue_key text not null` (normalized `venue + city`)
  - `name text not null`
  - `city text`
  - `lat double precision`, `lon double precision`
  - `followed_at timestamptz not null default now()`
  - `primary key (user_id, venue_key)`
  - Same RLS rules as `followed_artists` ([ADR 0006](../adr/0006-alerts-by-email-through-resend.md)).
- API routes: `POST /account/followed-venues`, `DELETE /account/followed-venues/{venue_key}`, included in `GET /account/alerts`.
- Daily Alerts integration (`alerts.py`): Include newly announced Concerts at Followed Venues in the same single daily Resend digest email (still capped at 1 email/day per Account, never sending the same Concert twice via `alerts_sent`).

## 4. Festival Lineup Taste X-Ray

Extend the existing festival Lineup feature:
- Opening a festival Ticket (or clicking **Full Lineup X-Ray**) groups the festival's entire source Lineup against the active Search/Taste into:
  1. **Matches for your Taste** (ranked best first using hybrid score: seed, 1-hop, Co-Billed, `pgvector` semantic, tags)
  2. **Undercard Discoveries** (matched Artists with lower Last.fm listener counts)
  3. **Full Lineup** (alphabetical/billed order, every Artist clickable for the Artist panel + Setlist + Watch Live).
