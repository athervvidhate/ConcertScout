# 04 - Platform and delivery research

Date: 2026-11-04. Method: web search snippets (one pass), not full page reads. Many results were vendor or aggregator pages. Anything not tied to a primary URL is marked UNVERIFIED. Verify prices and limits on the vendor page before committing.

## Bottom line

Recommended stack, simplest thing that fully works:

- Keep the Python agent (Google ADK) as one FastAPI service. Do not rewrite it in TypeScript just to get "one app". Cut it to 1 Uvicorn process, or 2 workers. cpu*2+1 Gunicorn workers is unjustified at low traffic and multiplies memory cost. Single container on Railway Hobby (about $5/month floor, usage-based) or Render at $7/month.
- Next.js on Vercel stays the UI. The route handler proxies and streams (SSE) to FastAPI. Vercel Functions with Fluid compute allow 300 s on Hobby and 800 s on Pro, which covers a 3-minute agent run, but a proxy that waits on a long upstream still bills active time. Consider the browser calling FastAPI directly for the stream, with a short-lived signed token, if proxy cost or timeouts bite.
- Persistence: add one Postgres (Neon, via direct signup or Vercel Marketplace) only when a feature needs saved runs or users. Use SQLModel/SQLAlchemy + Alembic on the Python side, since Python owns the data. Keep Redis (Upstash free tier or the Railway Redis) for cache, rate limits and the global spend counter. No second database.
- Auth: anonymous-first with a signed anonymous session cookie. Add Better Auth (new projects per Auth.js maintainers) only when saved profiles are needed. Spotify OAuth is a connector, not the login system.
- Abuse control: Cloudflare Turnstile on the first request of a session, per-session and per-IP limits, a global daily USD cap in Redis checked before every LLM call, and a kill-switch env flag. BYOK as an escape hatch later, not at launch.
- Tooling: uv + ruff + pyright (or ty, still beta, UNVERIFIED current status), pnpm, Biome, Vitest, Playwright, GitHub Actions, Renovate or Dependabot, gitleaks. No Turborepo: two packages in one repo do not need it. Generate the TypeScript client from FastAPI's OpenAPI.
- Observability: Sentry free for errors on both sides, plus Langfuse or Logfire for LLM traces. Pick one trace tool, not both.
- Delivery: one AGENTS.md (short), spec per ticket with acceptance criteria and a runnable verification command, vertical slices, CI as the gate, Vercel preview deploys, feature flags as plain env vars.
- Legal: privacy policy, cookie-light design, attribution links to Ticketmaster and Spotify, affiliate disclosure placed next to the links. The Spotify terms restrict storing Spotify content and using it for ML, which constrains persistence design.

## Current repo facts (from the tree, checked 2026-11-04)

- api/requirements.txt: pinned fastapi 0.115.13, google-adk 1.4.2, google-genai 1.21.1, spotipy, slowapi, redis 5.2.1, gunicorn. All dated mid-2025; expect drift.
- Root package.json has dev scripts using npm and a `test:concurrent` script with no real assertions. README says "Python 3.8+" while the pins target 3.12 (per a requirements comment). README states 60-second timeouts; recent commit extended it to 3 minutes. README lists Redis as "database". These are the mismatches to fix first.
- Two entry points (app.py, app_fallback.py, main.py) and two start scripts: candidates for deletion per the "no backward compatibility" rule.

## 1. App shape and hosting

Options:

A. Keep split (Next on Vercel, FastAPI elsewhere). Python has the ADK, spotipy and the best LLM tooling. Cost: two deploys, CORS or proxy, cross-language types (solved with OpenAPI codegen).
B. All TypeScript on Next (Vercel AI SDK, Mastra or similar). One deploy, one language, native streaming. Cost: rewrite of the agent, and loss of ADK. Only worth it if the agent logic is small. UNVERIFIED whether the agent is small; I did not read concert_scout_agent.
C. Python only on Vercel. Possible (Python runtime exists) but ADK dependency size and cold start are a risk. UNVERIFIED.

Recommendation: A, simplified. Rewrite cost of B buys little for a solo low-traffic app.

Vercel durations: the limits page (updated 2026-02-24) lists with Fluid compute 300 s default and max on Hobby, 300 s default and 800 s max on Pro/Enterprise for Node.js and Python. A different page mentions 1800 s on some plans; conflicting, UNVERIFIED. Source: https://vercel.com/docs/functions/limitations and https://vercel.com/docs/functions/configuring-functions/duration (search result summary, not fetched).
Streaming: Next route handlers can return a streamed Response; set `export const maxDuration`. Vercel Hobby is non-commercial per its terms (UNVERIFIED from memory), so a public app with affiliate links may need Pro ($20/month, UNVERIFIED).

Backend hosting prices (aggregator sources, UNVERIFIED, check official pages):
- Railway: Hobby $5/month including $5 usage, usage-based beyond; Pro $20. One source claims a 2026 price rise (Hobby +40%), figures unconfirmed. https://railway.com/pricing
- Render: web service $7/month (512 MB), $25 (2 GB); free tier sleeps after 15 min idle (bad for a 3-minute agent request cold start). https://render.com/pricing
- Fly.io: pay per second, smallest always-on machine from about $2.19/month; sources conflict on free tier. https://fly.io/docs/about/pricing/

Staying on Railway is fine. Switching platforms is not a priority.

Worker count: each Gunicorn worker loads ADK and holds memory. For I/O-bound async LLM calls, one Uvicorn process handles many concurrent requests. Use 1 to 2 workers, and ensure all state is in Redis (it already is). This also makes in-memory counters unreliable across workers, so keep limits in Redis.

## 2. Persistence

- Vercel Postgres and KV are sunset; stores moved to Neon and Upstash via the Vercel Marketplace (Q4 2024 to Q1 2025). https://neon.com/docs/guides/vercel-postgres-transition-guide ; https://vercel.com/blog/introducing-the-vercel-marketplace . A third-party claim of a June 2025 shutdown conflicts; UNVERIFIED.
- Neon free: scale to zero after 5 minutes, about 100 CU-hours per project per month, storage figure disputed (0.5 to 1 GB). Wake-up a few hundred ms. https://neon.com/guides/neon-vs-supabase-free-plan (vendor claim).
- Supabase free: whole project pauses after about a week of inactivity, two active projects. Bad for a low-traffic app unless pinged. Choose Supabase only if you want its Auth and storage.
- ORM: Python owns DB access, so SQLModel (SQLAlchemy + Pydantic) with Alembic. Drizzle or Prisma only apply if TypeScript talks to the DB; avoid two writers. Do not use Prisma/Drizzle and SQLModel on the same schema.
- Redis necessity: yes for rate limits, spend counter, and API cache. Upstash free tier: 256 MB, 500K commands per month, 10 GB bandwidth; adding a card moves to pay-as-you-go. https://upstash.com/pricing/redis . Railway Redis is the alternative; keeping it beside the API removes a network hop. Either works. Use TTLs on everything.
- Caching: Ticketmaster events (TTL hours; schedules change rarely), artist lookups (TTL days). Cache key by normalized query. Ticketmaster default quota is 5,000 calls/day and 5 requests/second per key, with Rate-Limit headers; one aggregator says 2/sec, UNVERIFIED. Deep paging is limited to about 1,000 results (third party, UNVERIFIED). https://developer.ticketmaster.com/products-and-docs/apis/getting-started/
- Spotify constraint: Spotify's terms restrict storing Spotify content and using it for ML (search summary of https://developer.spotify.com/terms and /policy, UNVERIFIED wording). Store Spotify IDs and your own derived fields (for example a taste summary), not raw catalog content, and re-fetch.
- Spotify API changes: since 2024-11-27 new apps cannot use Related Artists, Recommendations, Audio Features, Audio Analysis, Featured Playlists. https://developer.spotify.com/blog/2024-11-27-changes-to-the-web-api . Community staff posts say further dev-mode changes took effect Feb and Mar 2026 (forum, UNVERIFIED). Dev mode is limited to a small allowlist of users, UNVERIFIED current size. Check what the code calls before relying on any of this.
- Storing runs: table `runs(id, anon_or_user_id, input, output_json, model, tokens, cost_usd, created_at)`. This doubles as the cost ledger and gives share links. Defer until a feature needs it.

## 3. Auth

- Auth.js (NextAuth) is now maintained by the Better Auth team (announced 2025-09-22). Better Auth recommends itself for new projects, except for DB-less stateless sessions. https://www.better-auth.com/blog/authjs-joins-better-auth . A post dated 2026-07-07 says Better Auth is joining Vercel (UNVERIFIED beyond the vendor post). https://better-auth.com/blog/better-auth-joins-vercel
- Better Auth is TypeScript and wants a DB. With a Python backend, verify its session via a shared JWT or call the Next side. This adds coupling. Simplest: no accounts until needed.
- Clerk: hosted, fast, free tier (limits UNVERIFIED), adds vendor dependency and a JWT to verify in FastAPI. Supabase Auth: only if using Supabase.
- Anonymous-first: signed cookie holding a random session id; Redis holds the session; budgets key off it. Upgrade path: link session to account at sign-in.
- Music OAuth: Spotify Authorization Code with PKCE, tokens stored server side, encrypted, with refresh. It is a connection to a profile, not identity. Given Spotify's restrictions, consider offering "paste artists" or Last.fm username as the zero-OAuth path. Last.fm, Songkick and Bandsintown API terms were not checked: UNVERIFIED.

## 4. Abuse and cost control

Threat: unauthenticated endpoint that spends LLM and API money. Layers, cheapest first:

1. Global daily spend cap: Redis `INCRBYFLOAT spend:YYYY-MM-DD` with estimated cost per call; reject when over cap. This is the real safety net. Also set a hard budget limit in the Google Cloud/AI Studio console (check that the provider supports it; UNVERIFIED).
2. Kill switch: env var `CHAT_ENABLED=false` read per request (Railway env change redeploys; use a Redis key for instant effect).
3. Per-session and per-IP limits in Redis. slowapi by IP works but behind Vercel's proxy every request has the Vercel egress IP unless X-Forwarded-For is forwarded and trusted. Check this: if the route handler proxies, the IP slowapi sees may be Vercel's, making the limit global. This is a likely existing bug (UNVERIFIED, read the code). Forward the client IP in a header signed with a shared secret, and lock FastAPI to accept only requests carrying that secret.
4. Turnstile: free, privacy-friendlier than reCAPTCHA. Verify token server side once per session, then issue the session cookie. https://developers.cloudflare.com/turnstile/ (not fetched). Vercel BotID is an alternative, pricing UNVERIFIED.
5. Upstash Ratelimit (`@upstash/ratelimit`, `upstash-ratelimit` for Python) gives sliding window and token bucket over REST. Unneeded if you already run Redis with a small Lua or `slowapi` Redis storage.
6. Cap per-run cost: max tool calls, max output tokens, small model for routing, timeouts on every upstream call.
7. BYOK: user pastes their own Gemini key, stored only in the browser and sent per request. Adds a security surface; defer.

## 5. Tooling baselines

Opinions from experience unless a URL is given; all UNVERIFIED as 2026 status unless checked.

- Python: uv (lockfile, `uv sync --locked`, Docker multi-stage), ruff (lint + format), pyright (stable) or ty (Astral, beta as of my knowledge), pytest + pytest-asyncio, httpx + respx for mocking.
- JS: pnpm, Biome (single tool for lint+format, fine for a small app; keep ESLint only if `eslint-config-next` rules are wanted), Vitest for units, Playwright for one smoke test against a preview URL.
- Turborepo: not needed for two apps with different languages. Use a root `Makefile` or `justfile` with `make check` that runs everything. Reconsider only with several TS packages.
- Monorepo layout: `apps/web` (Next), `apps/api` (FastAPI), `docs/`. Currently `frontend/` and `api/`; renaming is optional.
- Typed contract: FastAPI emits openapi.json; generate TS types with `openapi-typescript` and a thin `openapi-fetch` client; CI fails if the committed generated file is stale. SSE events need their own documented schema (OpenAPI does not describe streams well).
- CI (GitHub Actions): jobs for api (uv sync, ruff, pyright, pytest), web (pnpm install --frozen-lockfile, biome, tsc, vitest, build), contract drift check. Required status checks on `main`.
- Dependencies: Renovate (grouped, automerge patch with passing CI) or Dependabot. The pinned ADK 1.4.2 and google-genai 1.21.1 are far behind; schedule one deliberate upgrade ticket.
- Secrets: GitHub secret scanning with push protection (free on public repos), plus gitleaks in pre-commit/CI. Rotate any key ever committed; check `git log -p` for `.env`.
- Delete: `.cache`, `app_fallback.py`, `start_fallback.sh`, root `package-lock.json` if moving to pnpm.

## 6. Observability

- Sentry: free Developer plan; SDKs for Next.js and FastAPI; first thing to add. Pricing in a vendor comparison: Team $26, Business $80. https://langfuse.com/compare/sentry
- Langfuse: Hobby free, 50k units/month, 30 days retention, 2 users; Core $29; self-host free. https://langfuse.com/compare/logfire
- Logfire (Pydantic): 10M spans/month free, then about $2 per million; OpenTelemetry-based, instruments FastAPI, httpx, Redis, and LLM calls. https://pydantic.dev/logfire/vs-langfuse (vendor claims)
- Google ADK emits OpenTelemetry traces (UNVERIFIED, check ADK docs). If so, either backend works via OTLP.
- Recommendation: Sentry + one of Logfire (best if you want the whole request path in one place) or Langfuse (best LLM-eval UX). Choose Logfire first for a Python-heavy backend. Vercel Analytics is already in package.json; keep it, and add Vercel logs only for the proxy.
- Always log structured JSON with run id, session id, token counts and cost per run. That table doubles as the spend ledger.

## 7. Agent-ready delivery

- AGENTS.md is the cross-tool convention (Linux Foundation / Agentic AI Foundation stewardship per secondary sources); Claude Code reads CLAUDE.md, and whether it also reads AGENTS.md is reported inconsistently, so make CLAUDE.md a one-line `@AGENTS.md` import. UNVERIFIED; check https://docs.claude.com/en/docs/claude-code/memory . Sources: https://www.tembo.io/blog/agents-md , https://blog.buildbetter.ai/agents-md-complete-guide-for-engineering-teams-in-2026/ (secondary).
- Keep it short (guides cite under 200 lines): exact commands (`make check`, `make dev`), layout, conventions that cannot be inferred, hard rules (never commit secrets, do not add fallbacks), and where specs live.
- Ticket/spec format that works: title; user-visible outcome; scope and out-of-scope; files or modules likely touched; acceptance criteria as testable statements; verification command(s); how to demo on the preview URL; rollback note. One ticket equals one PR equals one vertical slice (UI + API + data for one behavior), small enough to review in 15 minutes.
- Keeping the product working during the rewrite: strangler approach. Add CI and tests around current behavior first (one smoke test of the chat endpoint with the LLM and Ticketmaster mocked), then change one layer per PR, deploying to main only when green. Never have two parallel implementations long term; delete the old path in the same PR that makes the new one live.
- Preview deploys: Vercel creates one per PR for the frontend. Backend previews: Railway PR environments (UNVERIFIED availability on Hobby) or point previews at the shared dev backend.
- Review and verification: CI as the first gate; a second agent or `/code-review` pass on each PR; Playwright run against the preview URL for the golden path; agent attaches screenshot or trace in the PR.
- Feature flags: plain env vars or a Redis hash read at request time; no flag service at this size.
- Order of work (layers): (1) delete dead code, fix README, add Makefile + CI + one smoke test; (2) fix client-IP forwarding, add spend cap and kill switch; (3) Sentry + tracing; (4) OpenAPI codegen; (5) Postgres + runs table; (6) accounts and Spotify connect; (7) dependency upgrades.

## 8. Legal and compliance basics (not legal advice)

- Privacy policy and terms pages are required once you collect any personal data, including IP addresses in logs and the free-text prompts. State processors: Google (Gemini), Vercel, Railway, Upstash/Neon, Sentry, Cloudflare. The prompts may contain location and music taste.
- GDPR: if EU users, you need a lawful basis (Art. 6). Music taste alone is not a special category, but combined with other data it is personal data and profiling triggers transparency duties and the right to object (Art. 21). Practical posture: process only for the requested feature, retain runs for a short fixed period (for example 30 to 90 days), offer delete-my-data, and for Spotify connect use explicit consent. I did not retrieve the GDPR text or EDPB guidance in this pass: UNVERIFIED. Primary text: https://gdpr-info.eu/ or https://eur-lex.europa.eu/eli/reg/2016/679/oj
- Cookies: a functional session cookie needs no consent banner under ePrivacy in most readings, but Vercel Analytics is cookieless (vendor claim, UNVERIFIED). Avoid ad or tracking cookies and you can skip the banner.
- Attribution: Spotify requires its logo or icon wherever its content is shown, plus link-back and artwork rules. https://developer.spotify.com/documentation/design . Ticketmaster requires showing events per its branding guide and linking to its pages; rate-limit increases depend on compliance. https://developer.ticketmaster.com/products-and-docs/apis/getting-started/ . Exact Ticketmaster wording not retrieved: UNVERIFIED.
- Spotify terms also restrict ML training on Spotify content and long-term storage of it (see section 2). Sending Spotify data to an LLM for recommendations may be a gray area: UNVERIFIED, read the Developer Policy (https://developer.spotify.com/policy) before shipping that feature.
- Affiliate links (for example Ticketmaster via an affiliate network): FTC standard is a disclosure that is "difficult to miss and easily understandable", placed close to the link, not in a footer only (secondary summaries of 16 CFR 255). https://termly.io/resources/articles/ftc-affiliate-disclosure (secondary). A short "We may earn a commission" line next to the buttons plus a fuller page suffices. UK/EU have equivalent rules (ASA, UCPD): UNVERIFIED.
- The README says "Integration with Spotify and Ticketmaster". Make the UI footer credit both, as the existing "created by" footer shows the pattern.

## Open items for the next pass

- Read concert_scout_agent and the Next route handler to confirm: client IP handling, which Spotify endpoints are used, whether ADK is trivial to replace.
- Fetch primary pages for: Vercel limits and pricing, Spotify Developer Policy, Ticketmaster terms, Turnstile, Upstash Ratelimit, Neon pricing, Claude Code memory docs.
