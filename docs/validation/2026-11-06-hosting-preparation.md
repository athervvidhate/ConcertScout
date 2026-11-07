# Hosting preparation — November 6, 2026

Issue #31 remains incomplete. Prepared a real Vercel FastAPI export, runtime/function configuration and a concrete rollout in `docs/development/hosting.md`. Local/test settings cannot start the public entrypoint. Health wakes the function on Search-page mount without delaying input; a wake-up failure does not block a subsequent Search.

- `make check`: lint/types, 126 backend contracts and 19 frontend data tests passed.
- `make e2e`: production webpack build and all 18 browser checks passed at 1280px/390px. The empty-Search journey now aborts health and still completes a Search.
- Ten new public-configuration/entrypoint contracts passed, covering unsafe Redis, origins, published test secrets, IP header and Spotify redirect; errors omit private values. The actual entrypoint serves health with provider HTTP and Redis commands forbidden.
- Three fresh local imports/client constructions: 1798, 1130, 1108 ms; maximum RSS about147MB. These are not remote cold-start measurements.
- Existing local API health and frontend Privacy returned200 after the change. No production credentials were printed or changed.
- Read-only Vercel project/deployment inventory is recorded in the hosting guide. No project or deployment was deleted or promoted.

Pending evidence: domain choice, production Redis and real Turnstile configuration, optional Spotify credentials/registered redirect, a public end-to-end Search, genuine Vercel cold timing or an evidenced Fly.io move, and reviewed removal/verification of all old URLs. CI status belongs to the PR; local success does not complete these acceptance items.
