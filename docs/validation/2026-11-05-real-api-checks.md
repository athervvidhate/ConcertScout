# Real API and CI checks, 2026-11-05

## CI repair

PR #39 had the only failed GitHub CI job among PRs #33-40 at inspection: six frontend Search tests and two unhandled `window.matchMedia` errors. Tests still expected the former list UI, and the Poster stayed hidden when no candidates event preceded it.

The fix renders an already-received Poster without requiring candidates, resets presentation on a new Poster cycle, gives Ticket links descriptive accessible names, and updates Search assertions for the Poster/Ticket UI. Browser APIs are mocked only in tests. Dedicated tests exercise normal animation timing, reduced motion, and a Poster with no candidates event.

`make check` passed: 173 backend tests, 25 frontend tests, lint, formatting and types. `npm run build -- --webpack` passed. Default Turbopack still fails locally while binding its CSS worker port (`Operation not permitted`), including after requesting execution outside the sandbox. This is distinct from the GitHub test failures. The normal build remains in CI.

## Live checks

Keys came from the owner's ignored `api/.env`; no credentials were printed or committed. The API smoke checks used the backend at PR #40 commit `7eed2f2a43655abb1ecc2ff408f6d58c31dcfcf5`, which includes the pipeline through #21. Source caches were allowed, except the explicit Geoapify check used an empty test cache to ensure a real request.

- Real interpreter, with today's input fixed to 2026-11-05: “Something like Khruangbin in Chicago, next two weekends” produced Artist Khruangbin, place Chicago, dates 2026-11-06 through 2026-11-15.
- Uncached real Geoapify request resolved Chicago to 41.8755616, -87.6244212.
- Dated Khruangbin Search: 183 Concerts in the pool, five Recommendations, one successful real ranker call. All five Concert records exactly matched the source pool records.
- Tyler Childers in Chicago: 1,187 Concerts, eight Recommendations, one successful real ranker call. All eight Concert records matched the source pool. Lady A, LeAnn Rimes and Zac Brown Band were absent from the Poster.
- Place-only Chicago: eight Recommendations, source records verified, zero ranker calls.
- “hello there”: `needs_taste_or_place`, zero ranker calls.

A production webpack build of the repaired #39 frontend was served on port 3143 with that branch's real API on port 8000. In Yab, the dated Khruangbin Search completed with seven Recommendations from 183 Concerts; its first Ticket displayed date, reason, venue and Ticketmaster link, and selecting Dave Matthews Band changed the Ticket correctly. The T3 browser snapshot tool timed out twice, so Yab was used for this check.

Recommendation count and selection differ across model calls. This is a connectivity, data-integrity and UI smoke check, not a judged relevance evaluation. Automated CI remains mocked and requires no live keys.

## Still incomplete

Issue #23 remains a draft: fonts, coss controls, precise stage sequencing, animation geometry at 390px/1280px, and complete accessibility/design verification need work. Issue #22 still needs snapshot capture, judging and replay. These smoke checks do not replace those acceptance criteria. Last.fm and Spotify were not live-tested here.
