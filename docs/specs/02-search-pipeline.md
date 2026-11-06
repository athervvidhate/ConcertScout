# Search pipeline

One Search runs these steps in order. Only steps 1 and 6 use an LLM.

```
1. Interpret   Haiku turns text into a structured request
2. Resolve     Code geocodes the place and finds seed Artist IDs
3. Pool        Code gathers Concerts for the place and dates
4. Match       Code scores each Concert against the Taste
5. Shortlist   Code keeps the top 60
6. Rank        Haiku scores the shortlist and writes reasons
7. Assemble    Code rejects bad IDs and fills in facts
```

## 1. Interpret

A Pydantic AI agent with no tools returns:

```python
class Interpretation(BaseModel):
    artists: list[str]        # named seed Artists
    descriptors: list[str]    # plain Taste words, such as "dreamy guitar"
    tags: list[str]           # descriptors expanded into music tags
    place: str | None
    start: date | None
    end: date | None
```

The prompt receives today's date in code, which removes the old hardcoded 2025. `tags` must include related styles, because exact tags are sparse: the spike found 4 Artists tagged "shoegaze" in Chicago and none tagged "techno".

## 2. Resolve

Code geocodes the place, using Geoapify autocomplete in the UI and for free text. An LLM never geocodes. MusicBrainz resolves seed Artists to IDs at 1 request per second, and results cache for 7 days.

## 3. Pool

A pool holds every Concert for a place and date window.

- Query Ticketmaster with `segmentName=Music` and a 50-mile radius.
- Split the window into 30-day chunks to get past the 1,000-result cap.
- With no dates, use the next 6 months. That covers 85-96% of listed Concerts and costs about 7-8 calls for Chicago.
- Cache each chunk for 6 hours, keyed by rounded coordinates and month, so Searches share them.
- Always look up seed Artists directly, so a seed's Concert is never lost to paging.

With no place, skip the pool. Look up the seeds and the top 15 similar Artists by name. This costs about 16 calls.

Stay under Ticketmaster's 5 requests per second and 5,000 a day, with a shared limiter in Redis. All HTTP is async through `httpx`.

## 4. Match

Each Artist in the pool gets the best score it qualifies for. Join on MusicBrainz ID first, then on normalized name. 48% of Artists in the spike had no ID.

| Signal | Source | Base weight |
|---|---|---|
| Seed Artist | Search | 1.0 |
| One hop | ListenBrainz similar artists | 0.8 |
| Two hops, from a seed's top 15 | ListenBrainz similar artists | 0.5 |
| Shared tags | ListenBrainz tags, with rare tags worth more | 0.0 to 0.6 |
| Ticketmaster genre | Pool | 0.15, or 0.3 in narrow genres |

These weights are starting values. [The evals](06-evals.md) tune them.

Rules from the spike:

- Drop era and demographic tags before scoring: "gen z", decade tags, "seen live", and nationalities.
- Weight a tag by its inverse frequency in the pool, so "shoegaze" counts far more than "pop".
- Treat a Ticketmaster subgenre as narrow only if it holds under 30 Artists in the pool. "Pop" held 192 and was useless.
- If ListenBrainz similar-artists fails, fall back to Last.fm `artist.getSimilar`, then to MusicBrainz tags. The ListenBrainz endpoint is an unsupported Labs API, so it needs a tested fallback.
- Fetch tags in batches of 50 from the ListenBrainz metadata endpoint. Cache similarity and tags for 7 days.
- Scale a hop by how close the neighbour is, as a share of the list's top score. Listening counts fall off fast, so one hop uses the square root.
- Add up every two-hop path to an Artist, capped at 1. On the live Tyler Childers data a good neighbour had 5 or 6 paths and a miss such as Kim Petras had 1.
- Take seed tags from the MusicBrainz lookup, so tag matching needs no working similarity source. Without ListenBrainz at all, pool Artists have no tags and the seed, Last.fm and Ticketmaster genre signals remain.
- Break ties by adding up every signal an Artist has.

## 5. Shortlist

Keep the top 60 Concerts by score, deduplicated by Concert ID. Festivals count as one Concert, and the score comes from the best match in the Lineup.

A Search with no Taste has nothing to score, so it shortlists notable Concerts instead: those whose first Artist Ticketmaster links to MusicBrainz, once per first Artist, soonest first. The link costs nothing extra and leaves out most unbilled bar listings. It does not filter tribute acts.

This step emits the `candidates` event, whose names fill the loader. Names from a connected Spotify account never appear here, per [ADR 0003](../adr/0003-official-spotify-access-only.md).

## 6. Rank

A second agent, with no tools, receives short fields for each candidate: ID, Artist, genre, tags and match signal. It also gets the Taste. It returns:

```python
class Pick(BaseModel):
    id: str
    score: int        # 0-100
    reason: str       # one sentence, 140 characters at most
```

The ranker should drop poor fits. The spike showed tags pull in misses such as Kim Petras for Four Tet, and this step exists to remove them. Event text is untrusted, so it goes in delimited fields and the model has no tools. The prompt is one JSON object, so a listing's text stays inside its own quoted field, and each field is cut to 80 characters. The model never sees a URL, date, venue or price.

A Search with no Taste skips this step, so it makes one LLM call. The ranker gets 12 seconds, and any failure goes to the fallback.

## 7. Assemble

Code rejects any ID not in the shortlist, keeps one pick per ID, sorts by score, cuts to 8 and fills in facts from the source record. Only the reason comes from the model.

If the ranker fails, or every pick names an unknown ID, the Search shows the top matches from step 5 with a neutral reason built from the match signal. It says why the Concert matched, such as "Rhye is similar to Khruangbin". A ranker that returns no picks has not failed: nothing fits, so the Poster is empty.

The fallback never pads. A match qualifies with a signal other than genre, scoring above 0.15, the flat genre weight. A Concert with no match has no reason to show. Each Artist takes one slot, except a seed, so the Poster can be short.

A Search with no Taste shows the first 8 notable Concerts from step 5, each with the reason "Coming up nearby".

## API

```
GET  /health
GET  /nearby?lat=&lon=
POST /search            streams SSE
GET  /auth/spotify/login
GET  /auth/spotify/callback
POST /auth/spotify/disconnect
```

`/search` events:

| Event | Payload |
|---|---|
| `status` | `{step, message}` |
| `interpreted` | `{place, start, end, artists}` |
| `pool` | `{total}` |
| `candidates` | `{names, total}` |
| `poster` | `{recommendations}` |
| `error` | `{code, message, retry_after}` |
| `done` | `{}` |

Send a keepalive comment every 15 seconds. The browser sends `POST` with `fetch` and parses the stream, because `EventSource` cannot send a body.

## Module layout

```
api/concert_scout/
  app.py            FastAPI routes
  config.py         settings from the environment
  models.py         Concert facts and event payloads
  pipeline.py       the seven steps
  interpreter.py    step 1
  ranker.py         step 6
  assemble.py       step 7, pure functions
  matching.py       steps 4 and 5, pure functions
  similarity.py     one and two hops, with the Last.fm fallback
  sources/          ticketmaster, musicbrainz, listenbrainz, lastfm, geocoder
  cache.py          Redis helpers
  limits.py         rate limits and spend
```

`matching.py` makes no network calls, so tests can run it on fixtures.
