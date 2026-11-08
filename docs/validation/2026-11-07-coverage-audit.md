# Broad Concert coverage audit — November 7, 2026

## Decision

The coverage gap is substantial in this deliberately selected venue sample. **Test JamBase's API next; do not add Ticket Fairy to the live Search on the strength of this audit.** JamBase's public Lodge Room calendar contains the seven missing Lodge Room dates, making a bounded API trial worthwhile. Its public Baked Potato calendar has no upcoming Concerts, so it is not evidence that JamBase solves every venue gap. Targeted venue ingestion remains a useful later priority.

This is an offline developer tool and evidence, not a production multi-source integration. The app's Ticketmaster-only source scope is unchanged. No accounts, paid plans, affiliate links, partner applications, outreach or recurring scrapers were created.

## Method and limits

Reference window: **November 8–16, 2026**, venue-local dates. Selected three Southern California calendars: [Lodge Room](https://www.lodgeroomhlp.com/), [SOMA](https://www.somasandiego.com/events/) and [The Baked Potato](https://thebakedpotato.thundertix.com/). Initial HTML captured successfully. References are venue dates, not separate ticket tiers or sets. Nineteen source-backed dates span rock/pop-punk, folk/indie, hip-hop/electronic and jazz/funk/Latin programs; this is not a genre-balanced probability sample. Known gap venues are overrepresented. No national recall or overall recommendation-quality percentage follows from these numbers.

Two Lodge Room programs were excluded and recorded in the [manifest](../../api/evals/coverage-references.json): a design-talk program not verified as live music and a family tribute program whose title is not a performing Artist identity. That selection narrows the named-Artist audit; it is not a product decision to exclude family Concerts.

At **23:55:04 UTC**, made 20 Ticketmaster Discovery requests (venue + Artist/title keywords, US/CA, date bounds, no Music filter) and one Ticket Fairy California listing request. All lookups completed within one page each, with no HTTP/parse errors or truncation. Exact normalized published aliases for venue, city and Artist/title plus local date determined coverage. A failure would be unresolved, not missing. The queries did not invoke the app's matching or ranker.

A follow-up at 00:01:50 UTC on November 8 explicitly set `America/Los_Angeles` for Ticket Fairy's date bounds. It returned the same seven records and no reference matches, in 1.111 seconds including setup (1.086 seconds for the lookup). The final tool sends that time zone. Total successful provider requests across initial capture and boundary recheck: **22**. The initial capture and follow-up remain separate evidence files, rather than fabricating a combined wall-clock timing.

## Observations

| Reference calendar | Reference dates | Present in bounded Ticketmaster lookups | Missing from those lookups | Recovered by Ticket Fairy API |
|---|---:|---:|---:|---:|
| SOMA | 3 | 3 | 0 | 0 |
| Lodge Room | 7 | 0 | 7 | 0 |
| The Baked Potato | 9 | 0 | 9 | 0 |
| **Selected sample** | **19** | **3** | **16** | **0** |

The [chart](2026-11-07-coverage-audit.html) shows the same venue-date counts. Reproducible comparison code and source references are committed; full vendor captures stay ignored and owner-readable locally.

- **SOMA:** Father Of Peace (Nov 8), Underoath (Nov 10) and JSTJR (Nov 14) all appeared. External ticket links include TicketWeb. Underoath has multiple IDs; the tool flags this for review instead of counting it as two recovered dates. This supports the user's observation that external checkout does not always imply missing discovery.
- **Lodge Room:** Hit The Lights (Nov 8), The Tallest Man on Earth (Nov 11 and 12), Natural Child (Nov 13 and 14), Wrabel (Nov 15), Jamila Woods (Nov 16) were absent from completed venue and Artist keyword lookups. The exact dates are published in the venue's captured calendar.
- **The Baked Potato:** all nine reviewed dates were absent from the completed venue and Artist/title lookups. The calendar describes multiple inside sets and separate patio video tickets; the audit does not invent missing set times or equate patio tickets with inside seats.
- **Ticket Fairy:** the API returned seven California records in the window, including Lotus and Desert Dwellers in Northern California, but none agreed with the reference venue dates. This does not establish that Ticket Fairy adds no value in other Regions, dates or genres.

### JamBase feasibility, separated from API results

No JamBase key is configured. Its [official API onboarding](https://data.jambase.com/api/docs/getting-started) requires one, so no authenticated API capture or adapter was attempted. No API recall/cost claim is made.

Read-only inspection of [JamBase's Lodge Room calendar](https://www.jambase.com/venue/lodge-room) found all seven reference dates and matching Artists. Its [Baked Potato calendar](https://www.jambase.com/venue/the-baked-potato) says there are no upcoming Concerts. These public-site observations justify testing whether the API and intended plan expose the same useful dates. They are not counted as seven proven API additions. Earlier research details the non-commercial plan and access constraints; see [multi-source discovery](../research/2026-11-07-multi-source-concert-discovery.md).

## Cost and latency evidence

| Measure | Observed |
|---|---:|
| Provider API capture, including pacing | 7.639 seconds |
| Ticketmaster lookup time, summed | 6.359 seconds |
| Ticket Fairy lookup time | 1.151 seconds |
| API requests | 21 |
| Model requests / model spend | 0 / $0 |
| Local file read + typed parse + comparison | 0.0066 seconds, one warm-process observation |

Capture timing excludes prior venue-page fetching, human reference review, process startup and any production Search. The two source APIs required no paid subscription for these requests; no paid alternative-source account was used. Developer time includes manual identity review, so a cheap API fetch alone is not a maintenance estimate. Replay reproduced the original findings exactly and required neither keys nor network.

Default live snapshot: `api/evals/snapshots/coverage/live-2026-11-07.json`, 448,924 bytes, mode `0600`, SHA-256 `e17d0e70d7f63095a224784e0a0c11fa88768640c29d61bcb95d7b4c885cb873`. A check for configured credential values found none in the capture, reference manifest or selected-field test fixture. The frozen manifest includes hashes of the three raw reference HTML files, retained in the same ignored folder. Do not publish those full captures as a dataset.

## Implementation and validation

`python -m evals.coverage capture` makes explicitly bounded requests; `replay` recalculates the comparison from captured typed records. The tool retains statuses, external sellers, source-qualified IDs, query completeness and errors. It marks truncated pages, quota exhaustion and conflicting identities unresolved, rather than promoting them to coverage wins or omissions. [Usage and interpretation](../development/coverage-audit.md) describe the exact boundaries.

Validation: **254 API contracts passed**, including 12 coverage-audit contracts; ruff lint/format and strict pyright passed. Frontend lint/typecheck and **61 tests passed**. The replay CLI is tested with client construction and credential loading forbidden. Existing local frontend/API returned HTTP 200; neither service was restarted. No local browser suite was rerun because the production app and browser behavior are unchanged; PR CI still runs the repository's full checks.

Contracts cover external checkout, repeated-query ID deduplication, multiple sets/listings, incomplete queries, wrong location/date/name, cancellation, missing date, scope bounds, budget enforcement, real captured source fields, error privacy and offline replay.

## Follow-up order

1. Obtain a JamBase key through the owner's chosen free trial/Developer account, then run the same reference window or a newly verified window against the API under a small request ceiling. Confirm the seven Lodge Room dates and actual plan fields before writing a production adapter. Current evidence supports this modest next experiment, not a subscription upgrade.
2. If the API adds those dates, implement one source adapter and source-aware caching, deduplication and status handling. Test both source-pool coverage and whether named-Artist Searches can surface the added dates. Keep ingestion off the visitor's request path.
3. If jazz-room gaps remain, evaluate a permitted venue/ThunderTix feed rather than expecting a second broad API to fix it. Extend the reference sample to other US metros, independent rooms, orchestras and additional sellers before claiming broad US gains.
4. Pursue See Tickets display-feed access and scene-specific feeds once their incremental coverage and terms justify the maintenance. Ticket Fairy is deferred for this sample; its accessible endpoint alone is not a reason to change production.
