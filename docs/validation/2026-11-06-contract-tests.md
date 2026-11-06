# Contract test migration — 2026-11-06

Replaced 237 backend and 80 frontend tests with a smaller suite focused on promises at boundaries. The ordinary suite now has 106 backend contracts and 19 pure frontend data tests. Fourteen production-browser checks cover seven journeys at 1280px and 390px. Six opt-in checks exercise real providers.

Removed all component unit tests, simulated-DOM setup, timing/threshold mirrors, type/feature-existence assertions and hand-built Ticketmaster/Geoapify/MusicBrainz/ListenBrainz/Last.fm/Anthropic response shapes. The remaining model fixtures use the app's own structured output types. API tests replace typed source adapters and reject unexpected vendor HTTP. Browser tests use the actual API/pipeline and isolated real Redis; they do not assert that their domain fixtures represent an upstream API.

Preserved contracts for source facts and unknown IDs, missing facts, SSE completion and failures, origin/bot/IP/spend guards, logging privacy and cost accounting, cache/date/geography isolation, fallback/matching invariants, eval accounting and local file parsing. Browser tests cover Save across real navigation/reload/expiry, storage refusal, distinct Concerts sharing an Artist, no name flash for empty Posters, dropped streams and same-Search retry, local history privacy, explicit location use, and rotating examples/reduced motion.

The first browser run caught test races: reload began before Next navigation completed; an alert selector included Next's route announcer; an assertion assumed the wrong source label. Explicit navigation synchronization and scoped locators corrected those. No production behavior was weakened to pass.

The initial live Last.fm check wrongly assumed its catalog was always populated. Actual HTTP responses included valid empty lists, while other real requests returned 50 Artists. The corrected check compares adapter output to the actual response body, including an empty list. No automatic retry masks this variability, and no success body was fabricated.

Commands and boundaries are documented in [testing](../development/testing.md). Browser failure traces and screenshots are ignored locally and uploaded by CI for seven days. No paid provider calls run in ordinary CI; the real Cloudflare public test widget script still needs network access in browser tests.
