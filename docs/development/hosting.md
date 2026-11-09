# Hosting the two services

Both services are deployed, with public Search off until acceptance. This is the configuration and acceptance procedure, not evidence of a working public Search. The frontend and API stay separate, and the browser sends SSE directly to FastAPI (ADR 0001).

## Addresses and projects

`concertscout.app` is the public address. The owner rebought it through Vercel on November 6, 2026, and it uses Vercel nameservers.

| Service | Origin |
|---|---|
| Frontend | `https://concertscout.app` |
| API | `https://api.concertscout.app` |

`www.concertscout.app` and `concertscout.atherv.com` both redirect to `https://concertscout.app` with a 308. The frontend and API stay same-site, so Spotify's SameSite=Lax cookies work. `concertscout-api.atherv.com` is the old API host. Remove it from `concert-scout-api` once the new deployment is live.

Use the existing `concert-scout-ai` project for the updated frontend, rooted at `frontend/`, with Node 24 and `npm ci`. Create a separate API project rooted at `api/`, using its `.python-version` (3.13), `pyproject.toml` and locked runtime dependencies. `api/index.py` exports the real FastAPI app; `api/vercel.json` selects `iad1`, a 300-second function limit and excludes tests, eval Snapshots and environment files from the bundle. Upstash should be in the same region.

Spotify cookies are HttpOnly, Secure and SameSite=Lax. The apex and its subdomain work with the existing credentialed, exact-origin requests. Two unrelated `*.vercel.app` project hosts are different sites: do not claim Spotify works there or weaken cookie policy to make that setup appear complete. Ordinary Search can be checked on temporary hosts with their exact origin allowed.

## Production settings

Set secrets through the hosting dashboard or private CLI input. Never put values into this file, commit `.env`, copy developer tokens into a PR, or use `NEXT_PUBLIC_` for secrets. Check the exact frontend address before saving the allowlist.

| Service | Setting | Value or requirement |
|---|---|---|
| API | `TM_KEY`, `ANTHROPIC_API_KEY`, `GEOAPIFY_KEY`, `TYPESAFE_API_KEY` | Private provider keys |
| API | `LASTFM_KEY` | Optional private fallback/import key |
| API | `REDIS_URL` | Password-protected `rediss://` connection from Upstash; not its REST URL |
| API | `CORS_ORIGINS` | `["https://concertscout.app"]`; no trailing slash or wildcard |
| API | `CLIENT_IP_HEADER` | `x-vercel-forwarded-for`, only behind Vercel's edge |
| API | `TURNSTILE_SECRET` | Real production secret matching the frontend widget |
| API | `SEARCH_ENABLED` | Start with `false`; enable for the acceptance Search after settings are checked |
| API | `SEARCHES_PER_HOUR` | `10` starting limit |
| Frontend | `NEXT_PUBLIC_API_URL` | `https://api.concertscout.app`, without a trailing slash; set before building |
| Frontend | `NEXT_PUBLIC_TURNSTILE_SITE_KEY` | Public production site key restricted to `concertscout.app` |
| API | `RESEND_API_KEY`, `FEEDBACK_EMAIL` | Optional Search reports by email. The address must be the one on the Resend account |
| API | `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` | Optional official invite-only app credentials |
| API | `SPOTIFY_ENCRYPTION_KEY` | Stable private Fernet key, separately generated for production |
| API | `SPOTIFY_REDIRECT_URI` | Exact `https://api.concertscout.app/auth/spotify/callback`, also registered in Spotify |
| API | `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` | Optional accounts: the project's URL and publishable key |
| API | `SUPABASE_SECRET_KEY` | The project's secret key. Server only |
| Frontend | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | The same URL and publishable key; set before building |
| API | `CRON_SECRET` | Random string of at least 32 characters. Vercel's daily crons send it to `/warm` and `/sync`; unset, those routes do not exist |
| API | `JBD_API_KEY` | Optional JamBase Developer key. Only the daily `/sync` cron uses it; unset, Searches stay Ticketmaster-only |
| API | `JAMBASE_DAYS` | Optional catalog window in days, default 90, at most 180 |

The public entrypoint refuses to start with unencrypted or unauthenticated Redis, non-HTTPS or wildcard origins, published Turnstile test secrets, a missing trusted IP header, or a configured Spotify client using HTTP. Local `make dev` still uses the normal factory and local settings. Test environments can use Cloudflare's published test keys; public deployments must not.

Upstash holds the public cache, hashed limits, encrypted Spotify sessions and recorded spend. Keep its TLS connection private, select a region near the function and use the free tier or a deliberate budget cap. A stopped/reset database loses spend history; do not reset it as a way to clear a visitor limit. API spend guards use recorded usage, not a hard reservation against concurrent calls. Use the Anthropic and Typesafe accounts' spend controls as well.

## Preview connections

Configure `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_TURNSTILE_SITE_KEY` explicitly for Preview as well as Production. The build refuses missing API URLs, invalid or local API bases and published bot-test keys when `VERCEL=1` outside Vercel development mode; local development and the isolated browser suite retain their local/test configuration. This validation runs during the build and adds no work to a Search.

For a preview using the existing public API, allow that exact frontend origin in the API's `CORS_ORIGINS` and the hostname on the matching Turnstile widget. Preserve existing allowed origins, real bot verification and spend/visitor limits. Rebuild after changing public frontend values and redeploy the existing API revision after changing its runtime allowlist. A green frontend build and local browser suite do not prove those deployed connections work: check the real preview's endpoint, CORS preflight and one complete Search through the real widget.

## Accounts on Supabase

1. Create a Supabase project in US East, near the API's `iad1` region, and apply the migrations with `npx supabase link` and `npx supabase db push` from `frontend/`, with `--workdir ..`. Keep the project on asymmetric JWT signing keys, which new projects use by default.
2. Under Authentication, set the Site URL to `https://concertscout.app` and allow only the redirect `https://concertscout.app/auth/confirm`. Turn on email confirmation, an 8-character minimum password and secure password change.
3. Paste `supabase/templates/confirmation.html` and `recovery.html` into the Confirm signup and Reset password email templates. Their links carry a token hash to the confirm page, so they work in any browser.
4. Send auth email through Resend before opening sign-up, because Supabase's built-in mail only reaches the project team and sends two emails an hour. Resend's free plan allows 100 emails a day and 3,000 a month. Verify `concertscout.app` in Resend by adding its DNS records in Vercel, create a separate sending-only API key, then under Authentication → SMTP set host `smtp.resend.com`, port `465`, user `resend`, the API key as the password, and a sender such as `Concert Scout <accounts@concertscout.app>`.
5. For Google, create an OAuth web client in Google Cloud with the redirect `https://<project>.supabase.co/auth/v1/callback`, then enable Google in Supabase with its ID and secret. It needs identity scopes only.
6. The free plan pauses a project after a week without database activity, and a paused project stays down until the owner presses Resume in the dashboard. Requests do not wake it. The daily `/warm` cron makes one small database read to keep it active. Supabase also emails a warning about a week before pausing.
7. Accept by creating an account by email, signing in on a second device, signing in with Google, resetting a password and deleting a test account.

## Reviewable rollout

1. Confirm project settings, production Redis and real Turnstile pair. Add the exact OAuth redirect and invited Spotify accounts if enabling that optional shelf. Keep Preview and Production secrets separate.
2. Build the API from `api/` and the frontend from `frontend/`. Review deployment artifacts, domain assignments and environment-variable names before promotion. Run `make check` and `make e2e` against the same commit. These local checks do not substitute for public acceptance.
3. On the candidate API, verify `/health`, CORS preflight for `https://concertscout.app` and refusal of another origin. With Search on, run `scripts/check_visitor_limit.py https://api.concertscout.app --origin https://concertscout.app`. It proves the limit and that forged forwarding headers cannot reset it, with bad bot tokens that make no model calls. Check a second client from another network still gets through. Do not use a permissive proxy-header setting.
4. Open the real frontend, finish the real Turnstile check and submit one Search. Verify progressive SSE, a final Poster, source Ticket links, Save and reload, with no localhost requests. Confirm `/health` wakes on page load and a failed wake-up does not disable Search. Test Spotify consent/refresh/disconnect separately if configured; none of its Artists may enter `/search`.
5. Leave the API idle for at least 20 minutes. Without first opening the page or requesting health, measure submit-to-first-status on a direct Search and record whether a fresh instance actually handled it. Also record a warm control and a normal page-open-then-Search. One new deployment response may already be warm. Keep network timing separate from Python import timing. Do not store OAuth codes, tokens or Search bodies in diagnostic logs.
6. If a true cold first status exceeds 3 seconds, record the measured result and implement the spec's Fly.io move. Do not label local timings or the earlier throwaway function as production acceptance.
7. After the replacement full Search is accepted, remove old deployments/aliases and the unused `v0-concert-scout-frontend` project. Update `concert-scout-ai` rather than deleting the replacement. Verify each old URL is gone; deleting only a production alias leaves deployment URLs reachable. Remove `concert-scout-coldstart` if present in another scope. These destructive cleanup actions need an explicit reviewed inventory before execution.

## Deploying

- API: run `vercel deploy --prod --yes -p concert-scout-api` from `api/`. `api/.vercelignore` keeps `.env`, tests and Snapshots out of the upload, because the CLI does not read `.gitignore`.
- Frontend: `concert-scout-ai` is connected to Git, and Vercel blocks CLI uploads from it on a commit-author check. Push the branch, then run `vercel redeploy <its Git preview URL> --environment production`. The redeploy rebuilds with production settings.

## Inventory and current evidence — November 6, 2026

Read-only `vercel project ls` and `project inspect` under `atherv-vs-projects` found:

- `concert-scout-ai`: frontend root `frontend`, Node 22, existing production alias `concert-scout-ai-git-main-atherv-vs-projects.vercel.app`. It is also building current PR previews; build success is not a full public Search check.
- `v0-concert-scout-frontend`: project exists, no production deployments listed; it still needs reviewed deletion and verification of historical URLs.
- `concert-scout-coldstart`: not found in this scope. No project was deleted.
- `portfolio`: serves `https://atherv.com`; unrelated and must remain unchanged.
- `atherv.com` domain: `portfolio` also holds `avid.atherv.com` and `fireready.atherv.com`, and `workout.atherv.com` is a GitHub Pages CNAME. None of these change.

Three fresh local Python processes imported the full app and constructed its clients in 1798, 1130 and 1108 ms, using 146.6–147.9 MB maximum RSS on this Mac. No provider calls were made. These are local initialization measurements, not Vercel cold starts. The prior throwaway remote measurements remain in the platform spec.

Pending: moving production to the addresses above, public Search enablement and acceptance, production Spotify settings, cold timing, reviewed old-URL removal. Keep #31 incomplete until these are evidenced.

## Primary references

Checked November 6, 2026: [Vercel FastAPI entrypoint, lifespan and streaming](https://vercel.com/docs/frameworks/backend/fastapi), [Python versions, locks and bundle exclusions](https://vercel.com/docs/functions/runtimes/python), [Vercel request headers](https://vercel.com/docs/headers/request-headers), [Cloudflare test keys](https://developers.cloudflare.com/turnstile/troubleshooting/testing/). The broader trade-off research is [08-python-hosting](../research/08-python-hosting.md).

## Cached home examples

The authenticated nightly `/warm` job also builds the three public example Posters when Search is enabled, within the existing shared spend and Ticketmaster limits. These are the only additional model calls from the redesign. `/examples` reads the 30-hour Redis cache only; a miss or Redis outage returns an empty strip, never a paid fallback. Past source dates are filtered before delivery. Visiting the page and clicking an example makes no Search/provider/model call. The first strip appears after the next successful warm job; no deployment or environment change is needed.
