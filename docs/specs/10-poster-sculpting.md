# Instant Poster Sculpting

A Search currently ends at a static Poster of up to 8 Recommendations: if a visitor wants deeper cuts, a lower price ceiling, weekends only, or "more like card #3", they have to rewrite their Search from scratch. Poster Sculpting turns the Poster into a directly steerable surface without turning Concert Scout into a chat app.

This complements Issue #92 (*Refine a Poster with a typed follow-up*): both share the same short-lived pool session so visual controls and typed Refinements work seamlessly together.

## New Term (add to `GLOSSARY.md`)

- **Sculpt**: Adjust a Poster's filters or Taste balance using the Search's cached Concert pool, without re-fetching venues or running the interpreter. _Avoid_: chat, re-prompt.

## 1. Short-Lived Pool Session in Redis

When a Search finishes with a Concert pool:
- Store `session:{search_id}` in Redis with a **30-minute TTL** (separate from the 90-day `share:` snapshot, which holds only the final Poster).
- Payload:
  - `reading`: the Search's `Reading`
  - `pool`: the normalized list of source `Concert` records fetched for that place/window (capped at 1,500 Concerts)
  - `artist_tags`: the already-fetched ListenBrainz tags for pool Artists
  - `query_embedding`: the 512d query vector (when Hybrid Retrieval is active)
  - `taste`: seed Artists, ListenBrainz neighbours, and Co-Billing peers
  - `grades`: map of `concert_id -> int` already graded by Jev in this session (so untouched candidates are never re-billed)
- Never store visitor coordinates, IP addresses, or Spotify OAuth data in the session.

## 2. Sculpting Controls

### Tactile Dials & Filter Chips (above the Poster)
All filters evaluate strictly against source facts ([ADR 0002](../adr/0002-facts-never-pass-through-the-llm.md))—a Concert missing a price is never falsely marked as under a price cap:

| Control | Options | Behavior |
|---|---|---|
| **Discovery** | `Balanced` (default) · `Familiar` · `Deep Cuts` | Applies a popularity curve using cached Last.fm listener counts and venue capacity tier (when known). `Deep Cuts` boosts smaller rooms & lower-listener matches; `Familiar` boosts higher-listener matches. |
| **Budget** | `Any price` · `Under $40` · `Under $75` | Keeps Concerts with `price.min <= cap` (clearly notes how many listings had no source price). |
| **Days** | `Any day` · `Weekends only` | Keeps Friday–Sunday dates on the venue's local clock. |
| **Room** | `Any size` · `Intimate rooms` | Keeps Concerts at club/small-room capacity tier (when Venue Character is present). |
| **Festivals** | `Included` · `Solo shows only` | Toggles `concert.festival`. |

### Per-Ticket Taste Steering ("More like this" / "Not this vibe")
Each Ticket offers two lightweight steering actions:
- **More like [Artist]**: Adds the Artist to `boosted_artists` in the sculpt state.
  - Shifts the query vector using **Rocchio relevance feedback**: `q' = normalize(q + 0.6 * v_liked)` and injects that Artist's Co-Billing / ListenBrainz neighbours into the scoring pass.
- **Not this vibe**: Adds the Artist to `excluded_artists` in the sculpt state.
  - Drops that Artist from the Poster and shifts the query vector away: `q' = normalize(q - 0.5 * v_disliked)`.
- Active steering pills appear neatly beside the Reading chips with one-click undo (`×`) and a **Reset** action back to the original Poster.

## 3. API Contract

- `POST /search/{search_id}/sculpt`
  - Request body: `{discovery, max_price, weekends_only, intimate_only, hide_festivals, boost_artists, exclude_artists}` (strict Pydantic bounds, max 5 boosts / 10 excludes).
  - Security: same origin check, visitor limit bucket (`SCULPTS_PER_HOUR = 40`), and shared daily/monthly spend caps (no fresh Turnstile challenge required for an active session minted by a verified Search).
  - Execution:
    1. Load `session:{search_id}` from Redis (404 `session_expired` if older than 30 min → UI smoothly offers to rerun the Search).
    2. Apply hard filters + Discovery/Rocchio re-scoring in Python (**<30 ms**, zero Ticketmaster/JamBase calls).
    3. Take top 40 filtered shortlist; reuse cached Jev `grades` for filter-only sculpts (**$0, <50 ms**), or call Jev *only* for newly surfaced / Taste-shifted candidates (**~$0.0002, <1s**).
    4. Call Haiku `explain` only for newly promoted Recommendations lacking a reason for the current steering state.
    5. Return updated `Poster` + new `search_id` (so the sculpted Poster can also be shared via `/share`).

## 4. UI & Motion

- Reuses the existing Poster view transition (cards fade/lift out over 200 ms, new picks rise with 40 ms stagger)—no full Working View reset and no candidate-cloud replay.
- Reduced motion swaps cleanly without delay.
- If filters eliminate all picks, show an inline empty state naming which filter removed the candidates and a 1-click button to relax it.
