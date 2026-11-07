# Concert Scout

Concert Scout finds live music a person would want to see. It is being rebuilt in vertical slices: right now you type a plain-text Search and real Concerts from Ticketmaster stream in for the place and dates it names, with the closest matches to any Artist or style first. [docs/specs](docs/specs/00-overview.md) describes the full product.

- `api/`: FastAPI service, managed with `uv`
- `frontend/`: Next.js 16, React 19 and Tailwind 4

## Run it

You need [uv](https://docs.astral.sh/uv/), Node 24 and Redis (`brew install redis`).

```sh
cp api/.env.example api/.env   # then add TM_KEY, ANTHROPIC_API_KEY and GEOAPIFY_KEY
make dev                       # or `make start` for the frontend's production build
```

Open http://localhost:3000. `make check` runs lint, types and tests for both apps.


Testing: `make check` runs fast contracts, `make e2e` runs the production browser journeys at desktop and mobile widths, and `make check-live` opts into real-provider integration checks. See [the testing guide](docs/development/testing.md) for boundaries, setup and failure artifacts.
