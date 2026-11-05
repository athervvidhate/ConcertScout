# 11 - Artist similarity data without Spotify (as of 2026-11-04)

Method: live API calls from this machine on 2026-11-04/05, directory listings on data.metabrainz.org, and vendor docs. Items I could not confirm are marked UNVERIFIED.

## Recommendation

There is no public, bulk, regularly refreshed "similar artists" dataset you can download. The closest thing is a live API, not a file: the **ListenBrainz Labs similar-artists endpoint**. It returns MBID-keyed neighbours computed from listening sessions, and the docs say it is recomputed every Sunday. Do not mirror dumps; query it lazily and cache.

Stack, in order:

1. **ListenBrainz Labs `similar-artists`** is the primary source. Look up on demand per MBID, keep the top ~20 neighbours in a local SQLite or Postgres table with a 7-day TTL. Data is community listening data, so 2025-26 acts appear within weeks (tested below). Coverage is uneven for niche acts.
2. **Last.fm `artist.getSimilar`** is the secondary source for artists LB returns empty or tiny lists for. Allowed only while the app stays non-commercial, with attribution. Cache within HTTP headers and the 100 MB cap.
3. **MusicBrainz tags/genres via API** (`inc=genres+tags`) for a cold-start fallback: Jaccard overlap on genre tags between a seed and the candidate artists already in the event feed. Tags are CC BY-NC-SA, not CC0 (see 2).
4. **LLM** as a last-resort fallback only, and only to rerank a candidate set already in the feed (the events you actually have). Never to invent artists. Same role as in doc 01.
5. **Join key: MBID.** Ticketmaster attraction `externalLinks` likely carries a MusicBrainz id (UNVERIFIED in official docs, see 6); fall back to a MusicBrainz name search with a score threshold and a manual-override table.

Skip: ListenBrainz/MLHD+ dump processing, audio embeddings, Wikidata/Discogs ingestion. They add cost without improving freshness or indie coverage over the API.

Licence limits in one line: LB data is CC0 per MetaBrainz (commercial use allowed; they ask commercial users to pay as supporters); Last.fm is non-commercial only with attribution; MusicBrainz tags/genres are CC BY-NC-SA.

## Comparison

| Source | Type | Freshness | Licence | Indie / 2025-26 breakout | Fit for 512 MB |
|---|---|---|---|---|---|
| ListenBrainz Labs similar-artists | Live API, MBID in/out | Recomputed weekly (Sundays) per docs; algorithm string frozen since 2024 | MetaBrainz lists LB data as CC0; Labs endpoint itself has no stated terms or rate limit (UNVERIFIED) | Good for acts with ~thousands of LB listeners; empty for some (sombr: 0) | Excellent, lazy cache of a few MB |
| Last.fm artist.getSimilar | Live API, name or MBID | Continuous | Non-commercial only; attribution; revocable | Strong for mid-tier, weak for tiny acts (my judgement, not tested: no API key) | Excellent |
| MusicBrainz tags/genres | API or dump | Dumps twice weekly | Core CC0; tags/genres CC BY-NC-SA 3.0 | Tags sparse for new acts | API fine; dump 7 GB core |
| Wikidata (P136 genre, P737 influenced by) | Dump / SPARQL | Dumps ~weekly | CC0 | Poor: breakouts often lack items or influence links | Dump 104 GB json.bz2; no |
| Discogs dumps | Dump | Monthly | CC0 | Weak; no similarity, only aliases/members/groups | XML, large; no |
| LB listens dump, DIY | Build | Twice monthly full, daily incremental | CC0 (per MetaBrainz) | Best theoretical freshness | 240 GB listens dump; no |
| MLHD+ | Static dump | Frozen 2023-03 | Non-commercial only | None (stale) | 8 x 15 GB tars; no |
| LFM-2b / LFM-1b | Static | Withdrawn | n/a | None | Not downloadable |
| Music4All / Onion | Static | 2022-2025 releases | Onion CC BY 4.0 per aggregator (UNVERIFIED) | Stale, 109k tracks | Not useful |
| Spotify MPD | Static | 2018 | Restricted | None | Not available |
| Yambda | Static | 2025 paper | Apache 2.0 | Anonymised IDs likely (UNVERIFIED), no names to join | 195 GB; no |
| Deezer similar-artists graph | Static | 2021 | No licence file found (UNVERIFIED) | None | Tiny but stale |
| Audio embeddings | Build | n/a | Preview terms restrict | Cold start only | Heavy, fragile |
| LLM knowledge | Build | Model cutoff (June 2026 for current Claude) | Provider terms | Covers some 2025 acts, hallucination risk | Cheap per call |

## 1. ListenBrainz

**Labs similar-artists API.** Endpoint: `https://labs.api.listenbrainz.org/similar-artists/json?artist_mbids=<mbid>&algorithm=session_based_days_9000_session_300_contribution_5_threshold_15_limit_50_skip_30`. Official reference docs: none found; the best explanation is a developer reply in the MetaBrainz forum, https://community.metabrainz.org/t/how-does-similar-artists-work/678642 (reply dated 2024-02-07, fetched 2026-11-04). It says: listens from the past 9000 days are split by user and grouped into 300-minute sessions; artists co-occurring in a session each add a point to the pair; low-scoring pairs are dropped; one session's contribution is capped. It is listening-based, not tag-based. Only one algorithm string is live. Two later forum questions (2025-01-27, 2025-09-03) asking whether the endpoint is stable for external use or will join the main API have no visible answer. The cadence ("artist and track similarity is recalculated every Sunday") is from https://listenbrainz.readthedocs.io/en/latest/general/data-update-intervals.html (fetched 2026-11-04). Treat the endpoint as unsupported and keep a fallback.

**Live test results (2026-11-05 UTC)**, response time 0.5-2 s, JSON array of `{artist_mbid, name, comment, type, score, reference_mbid}`:

| Seed | Neighbours returned | Top results (score) |
|---|---|---|
| Massive Attack (classic) | 50 | Massive Attack/Radiohead/Bjork cluster, scores in thousands |
| Lola Young (2025 breakout, 10.4k LB listeners) | 7 | Lianne La Havas 32, Joesef 23, Ariana Grande 22, Rina Sawayama 20 |
| Geese (indie, 5.8k LB listeners) | 15 | Fontaines D.C. 45, Black Country New Road 31, King Gizzard 25 |
| Mk.gee | 51 | Vegyn 195, Toro y Moi 194, Blood Orange 171, Tame Impala 156 |
| Djo | 100 | Mac DeMarco 221, Crumb 193, The Strokes 163 |
| Wisp (Reid Dunn, electronic) | 94 | The Flashbulb 556, Aphex Twin 419 (plausible) |
| sombr (2025 breakout, 9.8k LB listeners) | 0 | Empty despite many listeners |

Takeaways: results look sensible for indie/alt acts, small lists for new acts, and total misses happen (sombr). Scores are raw counts, not normalised, so normalise per seed before mixing with Last.fm `match`. My attempt to look up "Wednesday" returned the wrong artist (Wednesday 13, a different band): name-only search resolves badly for common names, so MBID must come from a reliable link. Further MusicBrainz lookups for Alex Warren, Chappell Roan, Mannequin Pussy and Role Model failed because the MusicBrainz API throttled me; untested.

**Other LB endpoints (fetched 2026-11-04):**
- Popularity: `POST https://api.listenbrainz.org/1/popularity/artist` with `{"artist_mbids":[...]}` returns `total_listen_count` and `total_user_count`. Tested: sombr 174,554 listens/9,780 users; Lola Young 151,805/10,357; Geese 259,536/5,781. Useful for "is this artist big or small" gating. Docs: https://listenbrainz.readthedocs.io/en/latest/users/api/popularity.html.
- `GET /1/lb-radio/artist/{mbid}` needs `max_similar_artists` (400 without it); returns recordings, not artists. Not tested further.
- Rate limit headers: `X-RateLimit-Limit: 30` per window on the main API (observed). The Labs host sends no such headers (UNVERIFIED limits).
- `GET /1/stats/artist/{mbid}/listeners` works unauthenticated (tested).

**Dumps (listing at https://data.metabrainz.org/pub/musicbrainz/listenbrainz/, fetched 2026-11-05):** full listens dump 2026-11-01 is 240 GB (`.tar.zst`), a Spark-format 239 GB tar, statistics dump 23 GB, feedback dumps. Full dumps on the 1st and 15th; incremental daily; deleted listens are not removed from incrementals (docs, https://listenbrainz.readthedocs.io/en/latest/users/listenbrainz-dumps.html). Labs directory is frozen at 2020-10-22 (a 25 MB `recommendation.cf_recording` file): stale, no similarity dump is published. Licence: https://metabrainz.org/datasets/postgres-dumps lists the ListenBrainz PostgreSQL dump as CC0 and says commercial use is allowed but financial support is "strongly urged".

## 2. MusicBrainz, Discogs, Wikidata

- **MusicBrainz** (listing fetched 2026-11-05): core `mbdump.tar.bz2` 7 GB, derived `mbdump-derived.tar.bz2` 503 MB, JSON `artist.tar.xz` 2 GB; dumps twice weekly (latest 2026-11-04). Core is CC0; derived (tags, ratings, annotations, genres) and stats are CC BY-NC-SA 3.0 (https://musicbrainz.org/doc/MusicBrainz_Database/Download, https://metabrainz.org/datasets/postgres-dumps). Relationships carry members, collaborations, labels, and external URL links (Wikidata, Spotify, Bandcamp, etc.), but not similarity. A canonical dump (2 GB zstd CSV, 2026-11-03, CC0) maps recordings, not artists. API: 1 request per second per client (https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting); I was throttled after a burst of about 10 calls, so batch with sleeps.
- **Wikidata**: structured data CC0 (https://www.wikidata.org/wiki/Wikidata:Licensing, fetched 2026-11-04). Dumps: `latest-all.json.bz2` 103.6 GB (2026-10-27), truthy N-Triples bz2 43.6 GB (https://dumps.wikimedia.org/wikidatawiki/entities/). Has genre and "influenced by" properties plus MusicBrainz artist ID (P434), but influence links are sparse and almost absent for new acts (my judgement). Query a handful of items live via SPARQL rather than ingesting. Property usage counts UNVERIFIED.
- **Discogs**: dumps are CC0 (https://data.discogs.com/, fetched 2026-11-04), XML, monthly; file sizes not retrieved (UNVERIFIED). Provides aliases, members, groups, genres/styles on releases; no similarity or MBID link (UNVERIFIED mapping beyond names).

## 3. Last.fm

- `artist.getSimilar`: `artist` or `mbid`, optional `limit`, `autocorrect`; no user auth; returns name, mbid, `match` 0-1, url (https://www.last.fm/api/show/artist.getSimilar, fetched 2026-11-04). `artist.getTopTags` not fetched; tag-based, same terms (UNVERIFIED response details).
- Terms (https://www.last.fm/api/tos, fetched 2026-11-04): data usable "solely for non-commercial purposes" (3.1); commercial use without an agreement is a material breach (3.2); caching "in accordance with the HTTP headers" and a Reasonable Usage Cap of 100 MB (4.3.4); credit Last.fm with links (4.2.2); rate limits unpublished (4.4); no use of audio or images (5.1.8); Last.fm may share in revenue from future use. No AI/ML clause found. Caching is permitted, bulk mirroring beyond the cap is not. A 5 req/s guideline appears only in third-party summaries (UNVERIFIED).
- Quality: collaborative-filtering on a huge scrobble base, strongest for established artists; breakout acts show up with a lag (judgement, untested here for lack of a key).

## 4. Academic and open datasets

| Dataset | Status (checked 2026-11-04) | Notes |
|---|---|---|
| LFM-2b | Not downloadable: "not available for download anymore due to license issues" (https://www.cp.jku.at/datasets/LFM-2b/) | 2.01 B events, 120k users, 50.8 M tracks; withdrawn |
| LFM-1b | Same notice (https://www.cp.jku.at/datasets/lfm-1b) | 2016 data; withdrawn |
| MLHD+ | Available at data.metabrainz.org (8 x 15 GB tars, March 2023) | Non-commercial only per https://metabrainz.org/datasets/derived-dumps; stale 3 years |
| Music4All / Music4All-Onion | Zenodo record 6609677 (June 2022, later versions to 2025) | 109k tracks, 119k users; Onion licence CC BY 4.0 per an aggregator only (UNVERIFIED); built on Last.fm, so provenance risk; stale |
| Million Playlist Dataset | AIcrowd copy withdrawn; contact Spotify; Zenodo copy restricted | 2018 data; Spotify-sourced |
| Yambda (Yandex) | Hugging Face `yandex/yambda`, Apache 2.0, 4.79 B events, 1 M users, 9.39 M tracks, 195 GB (paper 2025-05-28) | No names or MBIDs found; cannot join to Ticketmaster (UNVERIFIED anonymisation) |
| Deezer similar-artists graph | GitHub `deezer/similar_artists_ranking`, 24,270 artists x 20 neighbours, RecSys 2021, last push 2021-10-17, no licence detected by GitHub | Stale; useful only as a benchmark |
| Deezer listening events | Zenodo, 700 M events, Mar-Aug 2022 (via search; licence UNVERIFIED) | Not artist-similarity ready |
| Pre-trained artist embeddings | Hugging Face API search ("artist embeddings", "artist similarity", "lastfm", "listenbrainz") returned only small or off-topic Last.fm recsys uploads | Nothing usable found; none maintained |

None of these gives 2025-26 coverage. Everything static is at least 1-8 years behind.

## 5. Build it ourselves

| Approach | Effort | Storage | Verdict |
|---|---|---|---|
| Session co-occurrence from LB dumps | Large: pull the 240 GB listens dump, run Spark or DuckDB sessionisation offline, ship a top-k table | Output about 20 neighbours x N artists; for ~100k artists about 30-50 MB | Duplicates what Labs already serves weekly. Only worth it if Labs disappears. Not sensible for a solo portfolio project |
| MusicBrainz tag overlap | Small: tags via API or the 503 MB derived dump | MBs | Do as the cold-start fallback only. Tag quality for new acts is thin; CC BY-NC-SA |
| Audio embeddings on preview clips | Large: preview sourcing, model hosting, vector index | 50k artists x 512 floats about 100 MB | Preview audio terms restrict analysis (check per provider, UNVERIFIED); skip |
| LLM knowledge | Tiny: one prompt per unknown artist, cache results | KBs | Acceptable fallback; cost per call is small but pricing UNVERIFIED here. Hallucination risk, so constrain to a candidate list |

For a 512 MB machine the lazy-cache design avoids any large artifact: with roughly 20 neighbours at ~50 B each (mbid plus score), 20k cached artists is about 20 MB.

## 6. Matching to Ticketmaster

- **Preferred: MBID from the attraction.** Ticketmaster attractions have an `externalLinks` object (listed in the Discovery schema, https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/, fetched 2026-11-04, but the docs show no example values). Third-party docs show `externalLinks.musicbrainz[].id`/`.url` with an artist MBID (https://www.withone.ai/knowledge/ticketmaster-discovery/conn_mod_def%3A%3AGK8OQAIK5wA%3A%3AiUy7xPokTgiKFEJilvyXJg/md, via search). The official docs do not confirm that key or how often it is populated. UNVERIFIED: check real attraction responses with the project's key and measure coverage before relying on it.
- **Fallback 1: MusicBrainz search by name** with Lucene `artist:"name"`, accept only score >= 95 and, when several candidates exist, disambiguate by popularity (LB `total_user_count`) and country. Name collisions are real: my test returned Wednesday 13 for "Wednesday".
- **Fallback 2: Wikidata or Last.fm link** from the attraction (`wiki`, `lastfm` entries per third-party docs) then Wikidata P434 to MBID, or Last.fm's returned `mbid` (can be empty for small acts).
- **Fallback 3: normalised name** (casefold, strip accents, "the", punctuation, "&" vs "and") in a lookup table keyed by event-feed names, with a manual override table. Persist resolved name-to-MBID pairs with a confidence flag; re-check low-confidence ones occasionally.
- Support acts: Ticketmaster attractions include openers, so every event is matchable to several artists, which improves recall.
- Last.fm neighbour names must be matched the same way (they come with `mbid` only sometimes), so resolve everything to MBID once in a single `artist_alias` table.

## Open items

- Check that Ticketmaster attractions return a MusicBrainz id and measure the hit rate on real data.
- Ask MetaBrainz (forum or email) whether the Labs similar-artists endpoint is supported, its rate limit, and the licence of the output (UNVERIFIED).
- Test Last.fm getSimilar on the same breakout set once a key exists, to compare against LB (sombr is the interesting case).
- Last.fm `getTopTags` terms and shape, Discogs dump sizes, Wikidata property counts: not verified.
