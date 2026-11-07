# Search pipeline

One Search runs these steps in order. Only steps 1 and 6 use an LLM.

```
1. Interpret   Haiku turns text into a structured request
2. Resolve     Code geocodes the place and finds seed Artist IDs
3. Pool        Code gathers Concerts for the place and dates
4. Match       Code scores each Concert against the Taste
5. Shortlist   Code keeps the top 40
6. Rank        Haiku grades the shortlist and writes reasons
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

Common genre aliases (UKG, DnB/D&B, RnB, EDM) are normalized in code, including source tags. The existing interpreter call expands other familiar genre and place shorthand without an extra model call. A small explicit place alias map resolves common local shorthand before geocoding; unfamiliar names and explicit qualifiers are preserved.

The prompt receives today's date in the visitor's own time zone, which the browser sends with the Search, so "this weekend" means their weekend. An unreadable zone falls back to UTC. `tags` must include related styles, because exact tags are sparse: the spike found 4 Artists tagged "shoegaze" in Chicago and none tagged "techno".

## 2. Resolve

Code geocodes the place, using Geoapify autocomplete in the UI and for free text. An LLM never geocodes. Of the first 5 results, the one with Geoapify's highest importance wins, so a bare "Manchester" means England rather than New Hampshire. A result under 0.8 confidence does not count as found, so the Search says it could not find the place instead of searching the wrong one.

Geoapify has no idea what Southern California or New England is. For an area that is neither one city nor one whole state, the interpreter returns a Region: the area's name, a large city near its middle as `place`, and `radius_miles`, capped at 500. Code geocodes that city, and the visitor sees the Region's name. MusicBrainz resolves seed Artists to IDs at 1 request per second, and results cache for 7 days.

## 3. Pool

A pool holds every Concert for a place and date window. A Geoapify state result in the US or Canada uses Ticketmaster `countryCode` and `stateCode`, for both pool and direct Artist lookups, instead of a circle around the state center. State cache keys are separate from city coordinates.

- Query Ticketmaster with `segmentName=Music` and a 50-mile radius, or the Region's own radius. Cache keys include the radius.
- Split the window into 30-day chunks to get past the 1,000-result cap.
- With no dates, use the next 6 months. That covers 85-96% of listed Concerts and costs about 7-8 calls for Chicago.
- Cache each chunk for 6 hours, keyed by rounded coordinates and month, so Searches share them.
- A Concert is over when its date has passed at its own venue, using the time zone Ticketmaster reports. The pool asks for one day earlier than the visitor's today, because a venue further west can still be on that day.
- Always look up seed Artists directly, so a seed's Concert is never lost to paging.
- A seed Artist's direct lookup covers every date Ticketmaster lists. Unless the Search sets an end date, all of them stay, so a tour past the 6-month pool still appears at no extra cost.

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
- Fetch tags in batches of 50 from the ListenBrainz metadata endpoint, starting each batch as soon as the pool has delivered 50 new Artists, so tagging overlaps the Ticketmaster pages. Matching waits only for the last batch. A Search with no Taste fetches no tags. Cache similarity and tags for 7 days.
- Scale a hop by how close the neighbour is, as a share of the list's top score. Listening counts fall off fast, so one hop uses the square root.
- Add up every two-hop path to an Artist, capped at 1. On the live Tyler Childers data a good neighbour had 5 or 6 paths and a miss such as Kim Petras had 1.
- Take seed tags from the MusicBrainz lookup, so tag matching needs no working similarity source. Without ListenBrainz at all, pool Artists have no tags and the seed, Last.fm and Ticketmaster genre signals remain.
- Break ties by adding up every signal an Artist has.

## Location

A Search can carry `near`, the coordinates the visitor already shared. It applies only when the Search names no place, and "near me" counts as naming none. A typed place always wins. Coordinates never reach a model.

## Parallel lookups

With a place, the Concert pool needs nothing from the Taste, so similar Artists and the pool run together. With no place, the pool waits, because it looks up those Artists by name.

## 5. Shortlist

Keep the top 40 Concerts by score, deduplicated by Concert ID. Festivals count as one Concert, and the score comes from the best match in the Lineup.

This step emits the `candidates` event, whose names fill the loader. Names from a connected Spotify account never appear here, per [ADR 0003](../adr/0003-official-spotify-access-only.md).

## 6. Rank

A second agent, with no tools, receives short fields for each candidate: ID, Artist, genre, tags and match signal. It also gets the Taste. It grades every candidate:

```python
class Fit(BaseModel):
    id: str
    level: int        # 0 a miss, 1 a stretch, 2 a fair suggestion, 3 a strong fit
    reason: str       # for level 2 or 3, one sentence, 140 characters at most
```

The ranker grades rather than chooses. Asked to choose up to 8, the model sometimes returned a full Poster and sometimes almost nothing for identical input. Grading every row against fixed levels leaves the choice to code.

Three votes run at once, each with the rows in its own fixed order, so no row gains from its place in the list. Each Concert takes its median level, and its reason comes from the most favourable vote. A vote that fails or misses the deadline drops out, and the others still count. On Haiku the three votes cost about three times one, a fraction of a cent. Thinking is off: with it on, the step took nearly twice as long and the grades were no better.

Both model answers are cached for 6 hours, the same as the Concert pool. The interpreter's is keyed by the visitor's date and the Search's words, and the ranker's by its exact prompt, so a repeated Search shows the same Poster and calls no model. Keys are hashed and never hold Search text.

The ranker should drop poor fits. The spike showed tags pull in misses such as Kim Petras for Four Tet, and this step exists to remove them. A seed Artist is never a poor fit, because the visitor asked for them. Event text is untrusted, so it goes in delimited fields and the model has no tools.

## 7. Assemble

Code rejects any ID not in the shortlist, any level below 2 and any row with no reason. It orders by level, then by match score, then by shortlist order, so only the model's level can move a Concert. It puts seed Artists first, keeps one Recommendation per Artist, cuts to 8 and fills in facts from the source record. A seed the model left out still appears, with a neutral reason. An Artist's other dates travel with their Recommendation, and two listings of one Artist on one date count once. If the ranker fails, or grades only unknown IDs, the Search shows the top matches from step 5 with a neutral reason built from the match signal. It says why the Concert matched, such as "Similar to Khruangbin".

## API

```
GET  /health
GET  /artist?name=
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
| `elsewhere` | `{keyword, concerts}`, only after an empty Poster |
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
  matching.py       steps 4 and 5, pure functions
  similarity.py     one and two hops, with the Last.fm fallback
  sources/          ticketmaster, musicbrainz, listenbrainz, lastfm, geocoder
  cache.py          Redis helpers
  limits.py         rate limits and spend
```

`matching.py` makes no network calls, so tests can run it on fixtures.

### Qualification and place-only Searches

The ranker grades poor fits below 2 and assembly leaves them out. If ranking fails, only matches with a score strictly greater than 0.3 qualify; genre-only and unmatched Concerts do not fill a Poster. Neutral fallback reasons describe the actual match signal. These thresholds are initial values for evaluation.

For a place-only Search, use Concerts whose headliner has a MusicBrainz ID in Ticketmaster as a practical proxy for notability. Keep the first Concert per headliner, soonest first, up to eight. This proxy may omit notable Artists without linked IDs.
