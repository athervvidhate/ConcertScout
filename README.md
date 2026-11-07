# Concert Scout

Concert Scout finds live music a person would want to see. It is being rebuilt in vertical slices: right now you type a city and real Concerts from Ticketmaster stream in. [docs/specs](docs/specs/00-overview.md) describes the full product.

- `api/`: FastAPI service, managed with `uv`
- `frontend/`: Next.js 16, React 19 and Tailwind 4

## Run it

You need [uv](https://docs.astral.sh/uv/), Node 24 and Redis (`brew install redis`).

```sh
cp api/.env.example api/.env   # then add your Ticketmaster key as TM_KEY
make dev                       # or `make start` for the frontend's production build
```

Open http://localhost:3000. `make check` runs lint, types and tests for both apps.
