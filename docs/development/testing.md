# Testing contracts

Tests should catch broken promises at boundaries. Do not add tests that only prove a feature exists, repeat a type declaration, mirror constants, or make an adapter agree with invented vendor JSON.

## Fast checks

`make check` runs lint, types, Python contracts and pure frontend data tests. It makes no real model calls. Coverage includes source facts, unknown IDs, SSE termination, safe errors, origin/bot/visitor/spend guards, telemetry privacy, cache/date scope, matching/fallback invariants, eval accounting and local file parsing.

API tests substitute typed Concerts, Places and Artist results at app-owned adapter functions. Unexpected vendor HTTP fails. They exercise real routing, pipeline and assembly, but do not verify external APIs.

## Browser journeys

Run `make e2e` after `make install`. Install Chromium once with `cd frontend && npx playwright install chromium`. Install `redis-server` locally if missing; CI installs it and the browser dependencies.

Browser journeys need the local Supabase stack, which `make e2e` starts. They run at 1280px and 390px: Search-to-Ticket source facts, distinct Concerts and Save through navigation/reload/expiry; empty Searches without a name wall; truncated streams and retry; local-history privacy; placeholder rotation and reduced motion; storage failure; explicit location use; isolated Spotify connection, shelf privacy and disconnect; denied Spotify access. Privacy opens without losing the active Ticket. Keyboard opening, Escape/focus restoration, reversible Ticket and photo bookmarks, removal and failed concurrent account removal verify saved state. A real recorded Calvin Harris Recommendation with eight additional dates checks intermediate expansion frames, a stable desktop photo and no photo enlargement or detail scrolling at the standard viewports. Collapsed dates must leave keyboard navigation. Save/Unsave feedback expires after completion. Demo checks include fully narrowed names before picks and opaque panel surfaces through reset; hero checks inspect visible library flap halves, aligned settled glyphs, palette agreement on each theme-change frame and reduced-motion static text. Delayed public examples cannot flash the green guide before the strip is placed; cache failure still reveals the guide. The captured seven-pick Tame Impala Poster checks long captions and duplicate-title removal in both palettes. Grid/List show the same Concerts for 0, 1, 2, 3, 4 and 8 picks at both widths and with/without reduced motion. Cached example clicks make no Search request even without Turnstile. Theme choice persists. Physical-phone animation acceptance remains separate.

The runner starts a separate production Next.js build on 3146, the real API/pipeline on 8146 and temporary isolated real Redis. It preserves the normal app on 3000/8000. Source adapters and the model are replaced at typed app-owned boundaries, without fabricated vendor response JSON. No production setting enables the test app.

The real Cloudflare browser widget uses its published test site key and needs access to its public script. Its server verifier is substituted at an app-owned boundary, so this suite does not validate Cloudflare. There are no private keys or paid model calls.

Failures retain traces and screenshots in `frontend/test-results/`; CI uploads them for seven days. No automatic retry hides a failure. Configuration follows the [Playwright web-server workflow](https://playwright.dev/docs/test-webserver).

## Accounts

`make check-accounts` starts the local Supabase stack and runs the `supabase`-marked API tests against it: real Auth tokens, the real Data API and real row-level security. They prove that one account cannot read or remove another's saves, that a browser cannot write rows past the API, that importing twice adds each Concert once, that tokens this project did not sign are refused, and that deleting an account needs a recent sign-in and removes its saves. Token expiry, audience, issuer and key rotation are checked without the stack in `test_tokens.py`.

The browser journeys also use the stack. They sign up through the real confirmation email in Mailpit, carry a save to a second browser, import guest saves, sign out, switch accounts, reset a password and delete an account. CI starts the same stack in the e2e job. Google sign-in needs a real Google client, so it is checked by hand against the hosted project.

## Real providers

`make check-live` opts into network calls using ignored `api/.env`. It checks actual Ticketmaster, Geoapify, MusicBrainz, ListenBrainz metadata, Last.fm and interpreter responses. Last.fm skips if its key is absent; the interpreter makes one paid call. Fresh caches prevent cached answers hiding API drift. These checks are excluded from ordinary tests and CI, with no fake-data fallback.

An unavailable provider or catalog can fail a check. Investigate and record the cause; do not change assertions or silently retry to claim reliability. The unsupported ListenBrainz Labs similarity endpoint is covered by fallback contracts at a typed seam; the live metadata check does not assert Labs availability.

Human relevance judgments remain separate. The 20 Search evaluation cases still need the owner's labels.
