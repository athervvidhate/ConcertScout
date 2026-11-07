# Platform

## Local first

All development runs on this computer, set up like a real server. Nothing depends on hosting.

- FastAPI under `uvicorn` in production mode on `127.0.0.1:8000`. No reload, and debug off.
- Real Redis locally.
- Real rate limits, CORS and spend counter, on by default.
- Next.js production build served on port 3000 when testing a full run, with `next dev` for UI work.
- Settings come from environment variables through `pydantic-settings`. `.env.example` lists every one.

One command starts everything.

## Python tooling

`uv`, ruff, pyright and pytest. Dependencies pin through `uv.lock`. Spotipy, gunicorn and ADK leave the project.

## Security

The browser calls FastAPI directly ([ADR 0001](../adr/0001-separate-python-agent-service.md)), so FastAPI protects itself.

| Control | Rule |
|---|---|
| CORS | An allowlist of exact origins, no wildcard. `/search` also refuses other origins on the server |
| Rate limit | Per client IP in Redis, hashed, read from the header named by `CLIENT_IP_HEADER`. Uvicorn runs with `--no-proxy-headers`, because otherwise it trusts a forged `X-Forwarded-For` from a local peer before the app sees it |
| Bot check | Cloudflare Turnstile token on `/search`, with test keys locally |
| Input | Search text capped at 500 characters, Taste lists at 100 names |
| Secrets | Server only. The frontend receives none |
| Errors | Clients get a code and a message, never a stack trace |
| Headers | CSP, HSTS, `X-Content-Type-Options` and `Referrer-Policy` |
| Outbound | HTTP clients have timeouts and retries with backoff |
| User-Agent | Identify the app and repo. Never a personal email |

The old app forwarded no client IP, so its limit applied to everyone at once. A test must prove the new limit is per client.

## Cost limits

| Limit | Starting value |
|---|---|
| Whole-app model spend | $10 a month. At the cap, Searches stop and home keeps working |
| Daily model spend | $1 |
| Per visitor | 10 Searches an hour, set by `SEARCHES_PER_HOUR` |

Measured cost is about $0.001 to $0.0013 per Search, from captured and live runs, so the $1 daily cap covers about 750 Searches. One visitor at the limit spends at most about $0.31 a day. Revisit this once the 20 judged Searches give a fuller measure.

`SEARCH_ENABLED=false` turns off Search. The spend counter lives in Redis and uses each call's real token counts. Without Redis, spend cannot be counted, so Search refuses rather than risk an unseen overspend, and the home page keeps working.

## Observability

Pydantic AI's OpenTelemetry output gives one trace per Search, with a span per pipeline step, token counts and cost. Traces must never hold Taste text or Spotify data.

## Hosting

The target is Vercel Hobby for both apps, because it is free and the project is non-commercial. Fly.io is the fallback, at about $1 to $4 a month.

Measured on 2026-11-04 on Vercel Hobby, with a throwaway FastAPI, `httpx` and Pydantic AI function:

| Measure | Result |
|---|---|
| Python imports | 0.92 to 1.16s, against 0.35s on a local Mac |
| Warm response | 0.18 to 0.28s |
| Streaming | 20 events arrived one second apart, so SSE is not buffered |
| First request after 20 minutes idle | 2.32s, one sample, from a new instance |

The first request after a deploy came from an instance already about 18 seconds old, so those samples say nothing about cold starts. The idle sample is the only true cold start measured. The real app imports more than this test did, so remeasure it during the hosting ticket.

Keep the experience fast with three measures:

1. Serve the page shell from the CDN.
2. Ping `/health` when the page loads, so the function wakes before a Search.
3. Show a real status right after submit.

Move to Fly.io if the first status takes more than 3 seconds after a cold start, or if Hobby's terms stop fitting.

Old Vercel projects `concert-scout-ai` and `v0-concert-scout-frontend` still exist. The hosting ticket removes them.
