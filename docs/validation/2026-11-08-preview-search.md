# PR81 Search connection incident — November 8, 2026

The owner reported that the Vercel preview stayed on “Reading your Search” and eventually reported that the API was not responding. This is reproduced in the real preview, independently of the passing local/CI browser journeys.

## Evidence

The real preview form submitted “Jazz in New Orleans this weekend”. Browser resource timing showed `/examples`, `/health` and `/search` targeting the preview's own hostname on **port 8443**. The UI eventually displayed “Concert Scout's API is not responding. Try again”. `NEXT_PUBLIC_API_URL` is absent in Preview, so `frontend/lib/search.ts` uses its local HTTPS fallback. Preview variable-name metadata shows only the legacy `BACKEND_URL`; the real public widget key is absent too, so the frontend uses Cloudflare's published local test key.

The production API `/health` returned 200. Its `/search` preflight from the exact PR81 branch origin returned **400, `Disallowed CORS origin`**. Therefore setting the URL alone will still leave the browser disconnected. The real production page's public JavaScript identifies `https://api.concertscout.app` and its existing real Turnstile site key; neither is a secret.

An initial request for the entire environment payload was rejected by automatic approval review because it could include unrelated secrets. That read was abandoned. The actual endpoint and failure were established from the browser, variable-name metadata and public assets instead. No server secret was read or changed.

The shared T3 browser stopped at Vercel login. The documented authenticated Vercel CLI full-URL request and the signed-in Yab CLI bridge reached the app. Only the diagnostic tabs were closed. No paid Search reached the API during reproduction: its target was the unreachable preview port.

## Prepared source repair

`frontend/next.config.ts` now rejects hosted builds with a missing/invalid public API base or a missing/published test Turnstile key. Local npm development, the isolated browser suite and `vercel dev` keep their existing local/test defaults. This is build-time validation, with no new runtime work or Search delay. The deliberate missing-setting build exits before producing a broken deployment.

The configuration regressions initially failed: 11 invalid hosted configurations were accepted, and a subsequent local-Vercel regression caught an overly broad guard before its development exemption was added. The final suite covers 13 cases. A real hosted-mode build using the proposed public API and widget settings succeeded. Frontend lint, types and all 76 data/configuration tests passed. The previous application's 96 browser journeys and five checks passed on `a596a1c`; those results do not prove deployed preview connectivity. No runtime UI or API source changed in this repair.

## Remote changes applied

With the owner's approval, the `fluid-search-redesign` Preview branch has `NEXT_PUBLIC_API_URL=https://api.concertscout.app` and the production widget's public key. The Turnstile widget allows the preview hostname. The API's `CORS_ORIGINS` adds the exact preview origin, and the deployed API revision was redeployed without promoting this branch's API source.

The rebuilt preview bundle targets `https://api.concertscout.app` with the real widget key. Preflight `/search` returns 200 for the preview and production origins and 400 for an unrelated origin.

The production API still runs the older source. It has no `/examples` route (404), so the preview's home strip and cached example Posters stay empty until this branch's API is deployed. Typed Searches use the unchanged Search contract. Only the branch alias is allowed: a per-deployment `concert-scout-*.vercel.app` URL fails CORS and the widget's hostname check.
