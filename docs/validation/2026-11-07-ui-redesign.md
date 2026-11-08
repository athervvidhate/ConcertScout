# Moss redesign acceptance — November 7, 2026

## Scope

The approved Fluid Search study is integrated with the production API contract. The owner chose Save only in the Ticket dialog. The branch includes the still-open accounts work (#77) and the approved design assets (#76), with no remote merge or production deployment.

The identity ships as standalone outlined SVGs for light, dark and pine surfaces; adaptive SVG/ICO favicon; Apple icon; and PNG exports, including a square Google app logo. Anton and Bricolage Grotesque load locally. No animation library was added: Motion handles React entrances and view transitions; native browser timelines reproduce the study’s coordinated pill/photo travel and walkthrough.

The live SSE pipeline, fact assembly, ranking, limits and Spotify isolation are unchanged. `/examples` is a Redis-only read. The authenticated nightly job builds three public Posters within the existing shared spend guards. Cache misses never start a model/provider call; expired source dates are filtered. The input's typing animation is isolated from the home photos/demo, and the optional account SDK loads as a separate chunk.

## Automated checks

- `make check`: lint, types, 253 API contracts and 61 frontend data tests passed.
- Local Supabase: 8 real ownership/account contracts passed.
- Browser acceptance covers 1280×800 and 390×844, 0/1/2/3/4/8 picks, both views, reduced/full motion, dialog focus/Save/reload/removal, source facts and omitted facts, grouped dates, nested Artist panels, imports, location privacy, isolated Spotify connection/shelf/paging/disconnect, accounts, reports, errors and retry, cached examples and theme persistence.
- The cached-example journey aborts the bot widget and asserts zero `/search` requests.
- Initial smoke: 8 browser checks passed. A subsequent broad run caught a removed dynamic grid selector; it was restored. One later mobile Close test raced the dialog's opening transition; journeys now await the completed popup opacity rather than treating a transparent entering dialog as ready.

Initial November 7 browser acceptance: **72 passed**, without retries (3.9 minutes). This verified functionality, not full animation fidelity; the November 8 follow-up adds intermediate-frame and interruption checks.

## Live checks

One real Search, “Something like Khruangbin in Chicago”, returned HTTP 200, a final Poster with 2 Recommendations and `done`, with no page errors. From the browser click, response headers arrived at 2.015 seconds and completion at 13.172 seconds; API telemetry recorded 11.136 seconds and $0.000717066. These are one local warm-path observation, not a production p95 or a cold-start claim.

The real nightly example builder successfully cached all three example Posters, with 7, 1 and 5 picks. It wrote only local Redis. The live home at port 3001 opened a cached Poster at 1280/light and 390/dark with zero Search POSTs, all eight rendered Ticketmaster images loaded, no page errors and no document overflow. Home, Poster and open Ticket screenshots were inspected. No account data or provider secrets were retained in evidence.

## Performance evidence and limits

The old fixed loader sequence is removed. The initial implementation exposed the Poster in about 18 ms after a fixture response but omitted the approved choreography; that measurement is superseded. The November 8 correction restores the study’s 950 ms narrowing hold and staged card/title reveal. See [motion acceptance](2026-11-08-motion-fidelity.md) for the current timings and frame sample. These finite presentation timings do not add network or model work.

Compressed first-party resources referenced by the prerendered home HTML, measured with Python gzip:

| Retained build | JavaScript | Fonts | CSS | Total |
|---|---:|---:|---:|---:|
| Earlier deployed-era local build | 324,429 B | 106,587 B | 8,874 B | 439,890 B |
| Accounts baseline before redesign | 390,524 B | 106,587 B | 9,159 B | 506,270 B |
| Redesign, accounts enabled | 323,708 B | 53,296 B | 11,145 B | 388,149 B |

The comparison is a retained local build comparison, not a production network trace. It excludes variable source photos, Turnstile and later dynamic chunks. With accounts configured, the separately loaded account SDK still downloads after hydration. These bundle sizes are the initial November 7 build; see the November 8 acceptance for the motion build. The font reduction is 53,291 compressed bytes; the redesign introduces no extra model call on a visitor's ordinary Search. The nightly three example Searches are additional paid work under the existing budget.

Physical-device frame rate, a screen-reader audit, real invited Spotify consent/refresh and real Google sign-in still need their separate acceptance. Automated Chromium and local Supabase checks cannot establish those. No production hosting, DNS or environment settings were changed.
