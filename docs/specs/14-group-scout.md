# Group Scout (`/g/[id]`)

Group Scout turns live-music discovery into lightweight multiplayer planning for 2 to 6 friends. Anyone can start a room with a place, optional dates, an optional budget, and their Taste, then share a link so friends can join without creating an Account.

Every Concert fact stays strictly source-backed from Ticketmaster and JamBase ([ADR 0002](../adr/0002-facts-never-pass-through-the-llm.md)). Spotify account data never enters a Group Scout room or any LLM ([ADR 0003](../adr/0003-official-spotify-access-only.md)).

## 1. Rooms and guest participation

- **Create (`/g`)**: A visitor chooses a place (geocoded via Geoapify), optional start/end dates, an optional per-ticket budget cap, their display name, and their Taste (typed/picked Artists or prefilled from their local Taste). The API fetches the place's Concert pool once (bounded and cached) and creates a room with a 128-bit unguessable capability ID (`[A-Za-z0-9_-]{22}`), expiring after 30 days.
- **Join (`/g/[id]`)**: Friends open the invite link with no sign-in required, enter a display name, their Taste (up to 100 Artists), optional available dates, and an optional max price. Rooms cap membership at 6 friends; leaving removes the member and cascades their votes.

## 2. Schema, RLS and live sync

Migration `supabase/migrations/20261122010000_group_scout.sql` adds three tables:

- `public.group_rooms`: `id`, `title`, `place` (`jsonb`), `start_date`, `end_date`, `max_price`, `concerts` (`jsonb`), `created_at`, `expires_at`.
- `public.group_members`: `id` (`uuid`), `room_id` (cascade), `name`, `artists` (`text[]`), `start_date`, `end_date`, `max_price`, `joined_at`.
- `public.group_votes`: `room_id` (cascade), `member_id` (cascade), `concert_id`, `vote` (`in` | `maybe` | `pass`), `updated_at`, primary key `(room_id, member_id, concert_id)`.

Row-level security allows `anon` and `authenticated` `SELECT` so browsers can subscribe to Supabase Realtime changes filtered by `room_id`, while rejecting direct client `INSERT`, `UPDATE`, and `DELETE`. All writes go through FastAPI with the server secret key, size/member-cap checks, and visitor rate limits. When Supabase Realtime is unavailable, the room UI falls back cleanly to lightweight polling while the tab is visible.

## 3. Fair intersection scoring (Nash social welfare)

Group ranking is deterministic and makes zero LLM calls:

1. **Constraint intersection**: Effective dates take the overlap (`max(start_date)` to `min(end_date)`) across the room and all members; if windows are disjoint, the API flags `dates_conflict: true` and falls back to the broader room/union window so the group sees options clearly instead of a silent empty page. Effective budget takes the tightest `max_price`; per ADR 0002, a Concert with no reported price never passes a strict cap.
2. **Per-member hybrid scoring**: Each member's Taste is scored against the eligible Concerts via `matching.score_concerts` using seeds, 1-hop similarity neighbours, live co-billing peers, ListenBrainz tags, and cached semantic vectors where available, yielding $s_m \in [0, 1]$.
3. **Nash social welfare**: For $M$ members, each Concert's group fit is:

   $$\text{NSW}(c) = \left(\prod_{m=1}^{M} (\epsilon + s_m)\right)^{1/M}, \quad \epsilon = 0.05$$

   A Concert that excites everyone (e.g. `[0.7, 0.7]` $\to 0.75$) beats one that only fits half the group (`[1.0, 0.0]` $\to 0.23$).
4. **Honest match badges**: Each Concert renders per-member badges directly from the member's winning signal—`Named`, `Similar`, `Co-billed`, `Sounds close`, or `Style match`—plus the matched Artist and seed `via` when present. No numeric score appears in the UI.

## 4. Live voting and calendar lock-in

- Members vote `In`, `Maybe`, or `Pass` on any Concert in the room (`PUT /groups/{id}/votes`), verified server-side against both the room's member list and source Concert pool.
- Live tallies update across browsers, a Consensus highlight marks Concerts where every member (2+) voted `In`, and a sort toggle switches between **Best group fit** and **Top voted**.
- Every dated Concert exposes 1-click `.ics` calendar export via `frontend/lib/calendar.ts` so the group can lock in plans straight from the Group Poster.
