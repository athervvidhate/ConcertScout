# Search pipeline

One Search runs these steps in order. Only steps 1 and 6 use a model.

```
1. Interpret   Haiku turns text into a structured request
2. Resolve     Code geocodes the place and finds seed Artist IDs
3. Pool        Code gathers Concerts for the place and dates
4. Match       Code scores each Concert against the Taste
5. Shortlist   Code keeps the top 40
6. Rank        Jev grades the shortlist; Haiku explains the Poster
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
- Once a day, at 23:00 UTC so the pools stay fresh through the US evening, Vercel's cron calls `GET /warm`. It runs the pool and tag lookups for a fixed list of busy cities (`warm.PLACES`, written the way the interpreter writes places so they geocode to the same point), one city at a time. Tags last 7 days, so a daily run keeps them warm; a pool lasts 6 hours. It calls no model and stops at the Ticketmaster daily limit.
- A Concert is over when its date has passed at its own venue, using the time zone Ticketmaster reports. The pool asks for one day earlier than the visitor's today, because a venue further west can still be on that day.
- Always look up seed Artists directly, so a seed's Concert is never lost to paging.
- A seed Artist's direct lookup covers every date Ticketmaster lists. Unless the Search sets an end date, all of them stay, so a tour past the 6-month pool still appears at no extra cost.

With no place, skip the pool. Look up the seeds and the top 15 similar Artists by name. This costs about 16 calls.

Stay under Ticketmaster's 5 requests per second and 5,000 a day, with a shared limiter in Redis. All HTTP is async through `httpx`.

### JamBase catalog

JamBase lists clubs and small rooms that Ticketmaster misses. With `JBD_API_KEY` set, a daily `GET /sync` (Vercel cron at 10:00 UTC, the quiet hours in the US) keeps a national copy in Redis, and a Search never calls JamBase. Visitors therefore cannot spend its quota or wait on it.

- The catalog covers the US for the next `JAMBASE_DAYS` days (default 90; the Developer plan allows 180). On November 7, 2026 the US held 14,706 events in the next 30 days and 34,632 in the next six months.
- The first runs download each state once, 100 events a page, resuming at the next state on the following run. A state that does not fit in what is left of a run waits for the next one. Nine states, CA through GA, took 152 calls.
- After that, each run asks for US events changed since the previous run (`dateModifiedFrom`, five minutes of overlap), then for the days newly inside the window. About 10,000 US events change in a week, roughly 15 pages a day.
- Listings live in one Redis hash per one-degree grid cell and month. A Search reads the cells its radius touches, or every cell its state holds, and filters by distance. A month's hash expires a few days after it ends. Changed events move cell, and cancelled, postponed, online-only and removed events leave. A Search with no place does not read the catalog.
- One Redis lock allows a single writer. Before any catalog request, `/v3/quota` must leave headroom under 900 calls a month, so the Developer plan's 1,000 included calls never overflow. The quota check itself counts as a call. A run lasts at most 240 seconds and keeps the last 60 for MusicBrainz.
- Reading a week near Los Angeles adds about 15 ms (p95 27 ms on a local Redis); a 90-day window, about 1,500 Concerts, adds about 50 ms (p95 160 ms).

### MusicBrainz IDs for catalog Artists

JamBase's Developer plan does not return MusicBrainz IDs, and tags and similarity need them. The sync resolves names itself:

- One MusicBrainz search resolves up to 20 names (`artist:"A" OR artist:"B" ...`, 100 results), through the shared one-per-second gate. A name takes the exact name or alias match. With several exact namesakes, the top one must lead by 5 points, so Bahamas resolves to Afie Jurvanen and a tie is left unresolved. A name crowded out of a full page is asked again later.
- Each run first takes Artists playing in the next 30 days in the busy cities (`warm.PLACES`) together with the 20 cells holding the most Concerts. The two lists usually agree but not always, so both count. Soonest Concert first. Then the queue of every other catalog Artist, soonest first.
- Answers are kept by normalized name. A name with no answer is asked again after 60 days. A Search attaches the IDs when it reads the catalog, so tags and similarity work for these Artists as for Ticketmaster's.
- On November 7, 2026 a pass settled about 950 names a minute and found IDs for 80% of them. Twelve sampled Los Angeles matches were all the intended Artist.

- A JamBase Concert is dropped as a duplicate when a Ticketmaster Concert on the same date has its headliner anywhere in the Lineup, shares a distinctive venue word, and starts within 90 minutes or has no known time. The sources spell venues and cities differently ("The Belasco" and "Belasco Theater", Hollywood and Los Angeles), so exact matching let a quarter of the catalog through twice. Ticketmaster's price and presales stay. Other rooms and early or late sets stay separate. On November 7, 2026, JamBase added 176 Concerts to the 216 Ticketmaster listed within 50 miles of Los Angeles for the coming week.
- JamBase has no price or presale. Its image is used only from JamBase's own uploads, never a default, and passes through the Next.js image cache. The footer and Privacy page credit JamBase, and its links carry `rel="nofollow"`.

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

Rank runs in two calls, neither with tools, and both see only short fields for each candidate: Artist, genre, tags and match signal, plus the Taste. Never a date, price or link.

**Grade.** Typesafe's Jev (`jev-1.14.0`) grades every shortlisted Artist in one request, one question per Artist named by its Concert ID:

- 3 strong: the same style, scene or sound. A seed is always 3.
- 2 fair: close in style, and many people with this Taste also like them.
- 1 a stretch: only a broad genre or one loose trait in common.
- 0 a miss: a different kind of music.

Jev returns a probability for each level. Each Artist takes the most likely level, the lower one on a tie, so a coin flip never lets a Concert in. Jev bills only input tokens, about $0.0002 a Search, and usually answers in well under a second.

**Explain.** After assembly picks the Poster, Haiku writes one reason for each Artist on it, and only for them:

```python
class Reason(BaseModel):
    id: str           # the row's number in this request
    reason: str       # one sentence, 140 characters at most
```

A reason tells someone who has never heard the Artist what they sound like, naming the style, scene, era or the similar Artist that brought them in. It never says the Artist suits the Search, and never mentions dates, venues, prices or links. If the reasons fail or miss their 8 second deadline, each Recommendation keeps its neutral reason from step 7.

Grading rather than choosing leaves the choice to code. Asked to choose up to 8, a model sometimes returned a full Poster and sometimes almost nothing for identical input. Against the owner's labels on 8 rated Searches, 5 runs each, Jev with Haiku reasons showed more liked Artists (89% against 76%) and fewer bad ones (4% against 9%) than three Haiku votes. It also repeated its Posters more closely (93% against 80% overlap), ranked in 3.0 seconds at p95 instead of 4.7, and cost a quarter as much. It found slightly fewer must Artists (88% against 94%).

The grades, the reasons and the interpreter's reading are each cached for 6 hours, the same as the Concert pool. The interpreter's reading is keyed by the visitor's date and the Search's words, the grades by the exact rows and Taste, and the reasons by their exact prompt. A repeated Search shows the same Poster and calls no model. Keys are hashed and never hold Search text.

The grade should drop poor fits. The spike showed tags pull in misses such as Kim Petras for Four Tet, and this step exists to remove them. A seed Artist is never a poor fit, because the visitor asked for them. Event text is untrusted, so it goes in delimited JSON fields.

## 7. Assemble

Code rejects any ID not in the shortlist and any level below 2. It orders by level, then by match score, then by shortlist order, so only the grade can move a Concert. It puts seed Artists first, keeps one Recommendation per Artist, cuts to 8 and fills in facts from the source record. Each Recommendation starts with a neutral reason built from its match, which Haiku's reason then replaces. A seed graded low still appears. An Artist's other dates travel with their Recommendation, and two listings of one Artist on one date count once. If grading fails, or returns nothing, the Search shows the top matches from step 5 with a neutral reason built from the match signal. It says why the Concert matched, such as "Similar to Khruangbin".

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
  warm.py           daily cache warming for busy cities
  limits.py         rate limits and spend
```

`matching.py` makes no network calls, so tests can run it on fixtures.

### Qualification and place-only Searches

Jev grades poor fits below 2 and assembly leaves them out. If grading fails, only matches with a score strictly greater than 0.3 qualify; genre-only and unmatched Concerts do not fill a Poster. Neutral fallback reasons describe the actual match signal. These thresholds are initial values for evaluation.

For a place-only Search, use Concerts whose headliner has a MusicBrainz ID in Ticketmaster, or a JamBase Artist ID, as a practical proxy for notability. Keep the first Concert per headliner, soonest first, up to eight. This proxy may omit notable Artists without linked IDs.
