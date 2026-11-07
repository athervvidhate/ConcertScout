# UI fidelity correction — 5 November 2026

Branch `23-ui-fidelity`, based on PR #39 at `b9ce79e3d8d245bfcabeeb882f136d5ae33941ca`.

The latest supplied reference image takes priority over the older font table: Anton reproduces its heavy condensed Poster lettering. Big Shoulders supplies Ticket artists; Bricolage supplies controls; Hanken supplies body/status; Doto supplies Ticket dates and prices. All fonts are self-hosted by `next/font`. The existing orange/ink/pink tokens remain. The Ticket is 940px wide at 1280px, with a perforated side, and the sun begins at 320px rather than radiating from the middle of every screen.

## Evidence

- `make check`: 173 API tests and 29 frontend tests; lint, formatting, Pyright and TypeScript pass.
- `NEXT_PUBLIC_API_URL=http://127.0.0.1:8144 npm run build -- --webpack`: production build succeeds. Default Turbopack remains the default build command. Added PostCSS configuration makes webpack apply the same Tailwind styling; the local Turbopack worker binding restriction is environmental.
- Production frontend: **http://localhost:3144/**. Isolated API: `http://127.0.0.1:8144`, with both localhost/127.0.0.1:3144 allowed by local CORS. Existing user servers on 3143 and 8000 were preserved.
- T3 preview snapshots failed twice with `Preview automation snapshot timed out after 15000ms.` Used Yab for actual rendered browser verification.
- Live browser Search: `emo rap san diego` returned 5 Recommendations from 60 close matches. The Ticket showed the source Concert `LIL PEEP 30TH BIRTHDAY CELEBRATION`, 14 November, House of Blues San Diego, 7 PM and its original Ticketmaster URL. No price appeared because none was supplied. Earlier live Chicago Searches also completed with 8 Recommendations from 60 candidates. This verifies the UI/data path, not Recommendation relevance quality.
- Deterministic comparison used a temporary fixture proxy, **only on port 8145**, forwarding the actual production HTML/assets and supplying clearly made-up SSE data from the approved mock. No demo names, counts, prices or links were added to production code. Local replay harness: `/tmp/concert-scout-ui/fixture.py`; comparison pages `/desktop` and `/mobile`.
- Actual iframe CSS viewport widths were measured as 1280 and 390. `documentElement.scrollWidth` equaled the viewport in both. At each width, 23 sampled grow-step frames had **zero overlapping name boxes**. The stress fixture also passed with an exceptionally long headliner, repeated Artist labels on distinct Concert IDs, and missing reason/time/price fields. Separate dated/venue-labelled buttons retained both Concerts.
- Save wrote source-backed Recommendations to localStorage, restored labels on a new Search, and advanced; Skip struck through the name and advanced. Enter activated the focused Save button. Unit tests cover IDs, tier assignments, persistence, timing/reduced-motion paths and exact source links. Local-storage failure is reported without claiming a save.

## Captures

[Desktop comparison](desktop.png), [390px comparison](mobile.png), [real browser Search](live-search.png).

These are browser screenshots, cropped/stitched from two viewport captures without changing the UI. Yab emits screenshots at 80% of the CSS dimensions, so the files are 1024px and 312px wide respectively. Screenshot scrolling caused a small sun-phase seam because the background rotates; no content was composited or invented.

The desktop reference proportions are reproduced closely. Mobile wraps the third tier onto another row and truncates the search input visually while preserving its full editable value. Very long headliners shrink to fit; duplicate Artist labels show source dates/venues. Source price ranges occupy separate lines in the Ticket side rather than breaking individual digits. Live counts and names naturally differ from the reference.

## Scope remaining

Save/Skip is the minimum real button interaction needed for the supplied screenshot and overlaps #24. There is no Saved Concerts page, expiry cleanup, or drag/swipe implementation in this correction. No physical mobile-device or drag acceptance is claimed. Recommendation judging remains #22. The PR does not merge, deploy, modify Vercel, or change backend/import/OAuth features.
