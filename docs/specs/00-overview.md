# Concert Scout rebuild: overview

Concert Scout finds concerts a person would want to see, from their taste and where and when they can go. It is a non-commercial portfolio piece that friends and visitors can really use. It should show Python skill in AI applications.

We rebuild in place in this repo. The old ADK app, its v0 frontend and its deployment scripts all go. Nothing stays for compatibility.

Terms follow [GLOSSARY.md](../../GLOSSARY.md). Choices with lasting trade-offs live in [the ADRs](../adr/), and the evidence lives in [the research notes](../research/).

## Specs

| Spec | Covers |
|---|---|
| [01-product](01-product.md) | What a person sees and does |
| [02-search-pipeline](02-search-pipeline.md) | How a Search becomes a Poster |
| [03-taste](03-taste.md) | Every way Taste gets in, including Spotify |
| [04-interface](04-interface.md) | Visual design, the loader and motion |
| [05-platform](05-platform.md) | Local running, security, limits and hosting |
| [06-evals](06-evals.md) | How we judge recommendation quality |
| [07-tickets](07-tickets.md) | The build order, as GitHub Issues |

## Decisions

| Topic | Decision |
|---|---|
| Purpose | Public, usable, non-commercial portfolio piece |
| Shape | A search product. No chat |
| Minimum Search | A Taste or a place. Everything else is optional |
| Backend | Python FastAPI service |
| Frontend | Next.js 16, React 19, Tailwind 4, coss ui, Motion |
| Model | Claude Haiku 5.5 (`claude-haiku-5-5`) for every LLM call |
| Agent library | Pydantic AI, with Pydantic Evals and OpenTelemetry |
| LLM calls per Search | Two: an interpreter and a ranker |
| Concert data | Ticketmaster Discovery only |
| Accounts | None in this rebuild. Saved Concerts live in the browser |
| Streaming | SSE directly from the browser to FastAPI |
| Money | $10-15 a month in total, no affiliate links, no ads |
| Development | Local, run like a production server |
| Address | `concertscout.app`, with the API on `api.concertscout.app` |

## Architecture

```
Browser (Next.js)
   |  POST /search, streamed SSE
   v
FastAPI service
   |-- interpreter (Haiku): Search text to structured request
   |-- geocoder
   |-- Concert pool: Ticketmaster, cached in Redis
   |-- Artist matching: MusicBrainz, ListenBrainz, Last.fm
   |-- ranker (Haiku): IDs to score and reason
   `-- code fills in facts from the source record
```

## Out of scope

Accounts, chat, other Concert sources, buying tickets inside the app, ads, and any paid tier.

## Open items

- Genre matching needs tuning against judged Searches. [The spike](../research/12-candidate-matching-spike.md) found it strong for country and punk and weak for electronic.
- The per-visitor limit is set from measured cost, not guessed. See [05-platform](05-platform.md).
