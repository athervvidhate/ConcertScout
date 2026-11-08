# Eventbrite authenticated organizer probe

Verified November 7, 2026 (capture timestamp November 8 UTC). Continues the [direct-feed research](https://github.com/athervvidhate/ConcertScoutAI/pull/79). No outreach, account changes, purchases or scheduled ingestion.

## Result

The owner's token authenticates, and `GET /v3/organizers/{id}/events/` returns public events belonging to unrelated organizers. This verifies a useful curated discovery route; it does not restore nationwide public search. The current [official reference](https://www.eventbrite.com/platform/api) still marks broad Event Search as shut down in December 2019. Organizer enumeration worked in the live probe but was not found in the current reference text, so treat its availability as provisional.

Tested organizer IDs: Bollywood In Hollywood `36278734843` and Bollywood Dreams Entertainment `1125166415`. The two responses contained seven records. The bounded adapter retained five: one in-progress listing was excluded (`status=started`) and one was categorized Arts, not Music. The retained records include the November 9 Karan Aujla unofficial afterparty at 33 Taps DTLA, a Washington DC afterparty, and three DJ/music parties in Washington and Oregon. Music category filtering can miss miscategorized music listings; it deliberately avoids treating every event from an organizer as music.

These are eligible source records, **not five confirmed coverage additions**. They have not been reconciled against Ticketmaster/JamBase or judged for relevance. This is a two-organizer sample, not national recall.

## Field support and product implications

| Needed fact | Verified response | Handling |
|---|---|---|
| Title and direct ticket link | `name.text`, `url` | Preserve exactly; display full title |
| Date/time/zone | `start.local`, `start.timezone`, `end.utc` | Preserve venue-local clock, exclude hidden starts and ended listings |
| Venue/location | Expanded `venue`, address and coordinates | Keep missing values absent; geographic filtering remains an integration step |
| Photo | `logo.url` | Event photo, not an Artist portrait |
| Price range | Expanded `ticket_availability` minimum/maximum `major_value` and currency | Preserve source range; no invented fees or presales |
| Sale status | `ticket_availability.is_sold_out` | Preserved separately; product needs a sold-out treatment before displaying these |
| Artists/Lineup | No structured performers in either capture | Empty Lineup; never extract a performer from an afterparty title |
| Genre | Music category, no Artist genres | Category alone cannot establish Taste similarity |

The Karan Aujla titles explicitly say **unofficial afterparty**. Turning the title into an Artist name would falsely suggest a Karan Aujla performance. The adapter leaves `artists=[]` even where a DJ is named in a title. This follows ADR 0002; a model is not used to fill the gap.

The existing Artist-based shortlist and Artist panel therefore cannot accept these as ordinary Artist recommendations. A next product change should display them as music events with their original titles, separate from verified Artist performances, and match only on explicit source/curated facts. It also needs source attribution, image handling, sold-out presentation, geographic filtering, conservative duplicate reconciliation, and removal on cancellations or disappearance from a complete organizer refresh. Do not simply append these records to the Artist pool: they would either be ignored or misrepresented.

## Implementation and reproducibility

- `concert_scout.sources.eventbrite`: async organizer adapter, fixed API host, secret in Authorization only, 10-second timeout, no retries; five-page limit per organizer. Rejects incomplete pages and organizer mismatches, and returns safe error codes. Filters private/unlisted/unshareable/online/non-Music/series-parent/hidden-start/in-progress/ended listings.
- `evals.eventbrite`: explicitly invoked CLI, up to five organizer IDs per run. Reads `EVENTBRITE_TOKEN` from ignored `api/.env` or environment. Saves normalized public facts only in a private local file; no account payloads, HTML descriptions, request headers or response headers. Eventbrite's rate-limit header includes credential material, so headers must never be logged or saved in evidence.
- Tests replay real selected-field captures from the successful organizer requests. Negative cases mutate those captures to exercise privacy, cancellation, category, incomplete pagination and safe upstream errors. No invented vendor fixtures or model requests.

From `api/`, with the token already configured locally:

```sh
.venv/bin/python -m evals.eventbrite \
  --organizer 36278734843 --organizer 1125166415 \
  --out evals/snapshots/coverage/eventbrite-probe.json
.venv/bin/pytest tests/test_eventbrite.py
```

The validation run made two organizer requests, one page each, returning five eligible records with no structured Lineups. The ignored normalized capture is `api/evals/snapshots/coverage/eventbrite-probe.json`. Single-request observations are not an average or p95, and this probe measures no production Search overhead. Production Search and scheduled jobs import none of this adapter, so this change adds no requests or work to Search.

## Remaining constraint

The [current API terms URL](https://www.eventbrite.com/help/en-us/articles/833731/eventbrite-api-terms-of-use/) redirected to a sign-in error through the owner's browser; `/platform/api-terms` returned no readable terms. The earlier report's cached terms are not current verification. Successful authentication demonstrates technical access, not permission for recurring third-party republication. Current display, retention, image and organizer-access terms remain unverified, so no recurring ingestion or production display is enabled here.

The owner has configured `JBD_API_KEY` in production. The JamBase code is still in open, unmerged PRs [73](https://github.com/athervvidhate/ConcertScoutAI/pull/73) and [78](https://github.com/athervvidhate/ConcertScoutAI/pull/78), with passing checks when read this session. Setting the key alone does not deploy those changes or trigger the initial national sync. Deployment and merging remain separate from this Eventbrite probe.

## Validation

Ruff lint/format, strict Pyright, 258 API contracts (including 16 Eventbrite cases), frontend lint/types and 61 frontend data tests pass. The browser suite was not rerun locally because neither the production composition nor UI changed; CI runs the existing browser journeys. No model calls were made by this probe or its tests.
