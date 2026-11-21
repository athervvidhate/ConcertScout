# Running it locally

For working on the app. The README describes the deployed product.

Install Python 3.13+, [uv](https://docs.astral.sh/uv/), Node 24 and Redis.

```sh
cp api/.env.example api/.env   # add TM_KEY, ANTHROPIC_API_KEY, GEOAPIFY_KEY and TYPESAFE_API_KEY
make dev                       # http://127.0.0.1:3000, API on port 8000
make start                     # the same, with the production frontend
make phone                     # the same, reachable from a phone on this network
```

YouTube refuses to play embeds on a page served from an IP address, so Watch Live shows "This video is unavailable" at `127.0.0.1`. Open `http://localhost:3000` to try it. Spotify sign-in still needs `127.0.0.1`.

The API runs without reload and uses real Redis, source APIs, limits and spend counters. `DEV_ORIGINS` lets `make dev` load through a tunnel host. [Spotify setup](spotify.md), [evals](evals.md) and [testing](testing.md) have their own pages.
