# 01 - Data sources research (as of 2026-11-04)

## Bottom line

Spotify is no longer a viable taste-input or similarity backbone for a hobby app. Since the February 2026 Dev Mode rules, a new app needs a Premium owner, is capped at 5 allowlisted users, cannot read other people's playlist contents, and (since Nov 2024) has no related-artists, recommendations or audio-features. Extended quota is open only to registered organisations with 250k+ MAU. The Developer Policy also bans using Spotify content to train or feed ML/AI models. Ticketmaster remains the only no-cost, self-serve, globally scoped event API that fits (5,000 calls/day, 5 rps), but it is mainstream-ticketing heavy, has a 1,000-item paging ceiling, and its terms limit caching and revenue. Indie coverage has no clean solo-dev source: Bandsintown, Songkick and (in practice) SeatGeek/AXS/DICE/RA are closed or partner-gated; JamBase is the best indie-friendly feed but only free for non-commercial use at 1,000 calls/month.

### Recommended stack

| Layer | Pick | Why |
|---|---|---|
| Taste input | Manual artist entry/search + Last.fm username (public top artists, no OAuth) + optional ListenBrainz username; optional Spotify login limited to the owner/5 users as a bonus, not a dependency | Only sources that work for arbitrary users without approval |
| Artist identity | MusicBrainz MBIDs as the join key | Free, 1 rps, used by Last.fm and ListenBrainz |
| Similarity | Last.fm `artist.getSimilar` (non-commercial) with ListenBrainz Labs similar-artists as the open alternative | Replaces Gemini "related artists" guesses with data |
| Events | Ticketmaster Discovery (primary) + JamBase (indie/long tail, if its terms permit) | See section 4 |
| Geocoding | Photon/Nominatim behind a cache for city-level, or Geoapify free tier; replace LLM lat/long | LLM-guessed coordinates are unnecessary |
| LLM role | Rank/explain from structured data only; never source of facts | Keeps Spotify/Ticketmaster term risk out of the LLM path |

Open decision: Last.fm TOS is non-commercial only. If the app is ever monetised (including Ticketmaster affiliate links), re-check. Ticketmaster's affiliate path and its "no revenue from the API" clause need reconciling (see 4).

---

## 1. Spotify Web API

**Dev mode vs extended quota** - https://developer.spotify.com/documentation/web-api/concepts/quota-modes (fetched 2026-11-04)
- Dev mode: up to 5 allowlisted users; non-allowlisted users can log in but get 403; owner needs Premium.
- Extended quota: since 2025-05-15 accepts applications only from organisations (individuals not eligible). Requirements: legally registered business, launched service, at least 250k MAU, key markets, commercial viability. Review up to six weeks. A hobby app cannot qualify.

**Feb 2026 changes** - https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide and https://developer.spotify.com/documentation/web-api/references/changes/february-2026
- New Dev Mode apps from 2026-02-11; existing apps migrated on 2026-03-09 (guide). Premium owner required; 1 Client ID per developer (raised to 25 in July 2026); 5 users per app. Extended Quota apps unaffected.
- Removed: batch GET tracks/albums/artists/etc., artist top-tracks, new-releases, browse categories, markets, `GET /users/{id}`, `GET /users/{id}/playlists`, user-scoped playlist create (use `POST /me/playlists`). Library save/follow endpoints replaced by `/me/library`. `/playlists/{id}/tracks` renamed `/items`.
- Search `limit` max 50 -> 10, default 20 -> 5.
- Removed fields: artist `followers` and `popularity`; track/album `popularity`, `available_markets`; `GET /me` `country`, `email`, `product`, etc. `external_ids` removal was reverted in March 2026 (https://developer.spotify.com/documentation/web-api/references/changes/march-2026).
- Artist `genres` field: not listed as removed in the changelog; still verify against a live response. UNVERIFIED in practice.

**Playlist reads**: the guide states playlist contents (`items`) are only returned for playlists the user owns or collaborates on; other playlists return metadata only. So "paste any public playlist URL" no longer works for new Dev Mode apps.

**Is the endpoint change postponed for existing apps?** Partly true, with a caveat.
- Official post (2026-02-06): "we have decided to postpone endpoint access changes for existing integrations"; Premium, user cap and one-Client-ID limits still applied to existing apps from March 9; no new timeline given. https://developer.spotify.com/blog/2026-02-06-update-on-developer-access-and-platform-security
- The March, May and July 2026 changelogs contain no announcement of the postponed endpoint changes taking effect, nor a rescheduled date: March = `external_ids` reversal; May = new `account_id` user field; July = Client ID limit 1 -> 25, quotas counted per developer account, new 429 `QUOTA_EXCEEDED` body. https://developer.spotify.com/documentation/web-api/references/changes/july-2026 , .../may-2026
- Caveat: the migration guide (which says the restrictions were applied to existing apps on March 9) and the February changelog (no grace period mentioned) read as if endpoint removal applies to all; developer reports say pre-2026-02-11 Client IDs still work for some endpoints (https://github.com/Osasuwu/like-current-song/issues/121). Treat as: grandfathered status is undocumented and could end without notice. Concert Scout's existing Client ID may still read public playlists; do not design the product around it. UNVERIFIED which exact endpoints the current Client ID still serves; test with the real credentials.

**Earlier removals (2024-11-27)**: Related Artists, Recommendations, Audio Features, Audio Analysis, Featured Playlists, Category Playlists, 30s previews in multi-get, and algorithmic/Spotify-owned editorial playlists, for new apps and existing Dev Mode apps without a pending extension request. https://developer.spotify.com/blog/2024-11-27-changes-to-the-web-api . Available-genre-seeds ties to Recommendations; status UNVERIFIED.

**Login for users**: possible via OAuth, but Dev Mode caps at 5 allowlisted users, so it cannot serve the public.

**Developer Policy, AI/LLM** - https://developer.spotify.com/policy
- III.14: do not use the Spotify Platform or any Spotify Content to train a machine learning or AI model (covers ingesting content into such models).
- III.13: do not analyse Spotify Content or the Service for any purpose (incl. building user profiles/benchmarking).
- Metadata/cover art need a link back; may not be offered as a standalone service (II.4.2, II.4.3). Commercial use of non-streaming apps limited to ads/sponsorship/access sales (IV).
- Implication: passing Spotify playlist/artist data into Gemini or any LLM prompt is a likely policy violation. Strongest reason to drop Spotify as the LLM's input. (The page did not address caching; Developer Terms not read.)

---

## 2. Taste-input alternatives

| Source | Access / cost | Auth | Provides | Verdict |
|---|---|---|---|---|
| Last.fm | Free API key; non-commercial only (commercial needs agreement) https://www.last.fm/api/tos | None for public profiles (username + api_key) | `user.getTopArtists`, loved tracks, recent scrobbles (method names from general knowledge, UNVERIFIED this session) | Best: no OAuth for public data. Limited to people who scrobble |
| ListenBrainz | Free, open | User token only for writes; public stats by username (UNVERIFIED endpoint names) | Listens, stats, LB Radio https://listenbrainz.readthedocs.io/en/latest/users/api/core.html | Good secondary, small audience |
| MusicBrainz | Free; User-Agent with contact required; ~1 req/s per IP https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting | None | Artist IDs, names, tags. Not user taste | Identity layer. Core data licence is CC0 per MetaBrainz (UNVERIFIED this session) |
| Apple Music API / MusicKit | Requires paid Apple Developer Program ($99/yr, from general knowledge) | Developer token + Music User Token; user needs a subscription | Library, playlists, heavy rotation, catalog similar-artists view | Viable for users, but cost and subscriber-only. Details UNVERIFIED (docs page did not render) https://developer.apple.com/documentation/applemusicapi/ |
| YouTube / YouTube Music | No official YouTube Music API; YouTube Data API v3 default 10,000 units/day https://developers.google.com/youtube/v3/getting-started | Google OAuth | Playlists, likes (generic video data, weak artist mapping) | Poor fit |
| Deezer | Terms: non-commercial only, no revenue, access revocable at will https://developers.deezer.com/termsofuse ; a third-party README says new app creation ended (UNVERIFIED) | OAuth for user data | Artist related endpoint (not verified) | Avoid for new build |
| Tidal | Official developer portal not reachable this session; only unofficial/private API docs found | - | - | UNVERIFIED; do not depend |

Spotify import, if wanted: user pastes artist names or uses CSV/privacy-export; no API dependency.

---

## 3. Artist similarity without Spotify

- **Last.fm `artist.getSimilar`**: returns name, MBID, `match` score 0-1, url, images; free key, no user auth, error 29 on rate limit. https://www.last.fm/api/show/artist.getSimilar . TOS: non-commercial only; caching required per HTTP headers with a 100 MB "reasonable usage cap"; "powered by AudioScrobbler" attribution; no AI clause found; rate limits at Last.fm's discretion (no number published). https://www.last.fm/api/tos . Quality: collaborative-filtering based, strong for mainstream and mid-tier, weak for tiny acts (my judgement).
- **ListenBrainz**: `GET /1/lb-radio/artist/{seed_artist_mbid}` returns recordings from similar artists (modes easy/medium/hard). https://listenbrainz.readthedocs.io/en/latest/users/api/core.html . Labs endpoint `labs.api.listenbrainz.org/similar-artists` takes `artist_mbid` and an `algorithm` string; scores from track co-occurrence in listens; low-listen artists get weak results; maintainers noted datasets were still limited (MetaBrainz blog and forum, via search; no official reference found). Open data; rate limits and exact licence UNVERIFIED.
- **MusicBrainz**: tags and relationships (members, side projects, labels), not similarity. Useful for genre tags and enrichment.
- **Apple Music** catalog `view/similar-artists`: exists per general knowledge, needs paid developer account; UNVERIFIED.
- **Deezer related**: see terms above; avoid.
- **LLM**: acceptable only for explanations, or for a last-resort fallback when no source knows the artist.

---

## 4. Event data

### Ticketmaster Discovery API v2 (primary)
- Free key, instant, 5,000 calls/day and 5 rps default; increases by case if TOS/branding compliant. https://developer.ticketmaster.com/products-and-docs/apis/getting-started/
- Deep paging: `size * page < 1000`, so max ~1,000 results per query. `latlong` is deprecated in favour of `geoPoint` (geohash). https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/ . Design: split queries by date window / classification / keyword.
- Coverage: US, CA, MX, AU, NZ, UK, IE and other European countries; mainstream venues. Indie/DIY shows largely absent (judgement).
- Terms (https://developer.ticketmaster.com/support/terms-of-use/): no caching/storing Event Content "other than for reasonable periods" (undefined); remove any content within 24h on request; no replicating the Ticketmaster experience; no deriving revenue from the API "whether for direct commercial or monetary gain or otherwise". No AI/LLM clause found and no attribution requirement on that page; branding guide referenced for quota increases. Page date not shown. Fetched summary might be partial; read the full TOS before launch.
- Affiliate: Impact network; add your Impact publisher ID in the developer portal so tracking is appended to Discovery event URLs; sign up per country; purchase/Partner Commerce API is restricted to select partners. https://developer.ticketmaster.com/partners/distribution-partners/affiliate-sign-up (via search). Commission rates UNVERIFIED (third-party sources conflict). Tension with the "no revenue" clause UNVERIFIED; ask Ticketmaster.
- Status: International Discovery API being consolidated into Discovery; plan around Discovery.

### Others
| Source | Solo-dev access | Cost | Notes |
|---|---|---|---|
| JamBase | Self-serve key | Developer: $0, non-commercial, 1,000 calls/month, 3,600/hr, 6-month future window, $0.05 overage (no hard stop). Startup $500/mo ($6,000/yr) 20k calls; Pro $1,500/mo; Pro+ $2,500/mo. https://data.jambase.com/pricing | Attribution required on all plans. Strong live-music/indie focus, external IDs across platforms (third-party listing). Caching/AI terms not read: UNVERIFIED |
| SeatGeek | Client ID from developer portal; portal did not render this session. Terms last updated 2025-03-17 https://seatgeek.com/api-terms | Free (UNVERIFIED) | Terms say a separate agreement may be required; approval criteria, rate limits, caching UNVERIFIED. Mainly ticketing/sports/mainstream |
| Bandsintown | Artists and their reps only; others via partnership. Key from Bandsintown for Artists settings https://help.artists.bandsintown.com/en/articles/3372745 ; Data Application Terms https://corp.bandsintown.com/data-applications-terms | n/a | App IDs personal and non-transferable; scraping barred. Not usable |
| Songkick | Not approving hobbyist/student/educational requests; partnership agreement plus licence fee https://www.songkick.com/developer | Licence fee | Acquired by Suno (reported late 2025; secondary source). Not usable |
| Eventbrite | Event search endpoint shut down 2019-12-12; API only for your own org's events https://www.eventbrite.com/platform/docs/changelog (via search) | - | Not useful for discovery |
| setlist.fm | Free key via form, header `x-api-key`; free for non-commercial only https://api.setlist.fm/docs/1.0/index.html | Free | Past setlists only; upcoming events not documented. Useful for "what do they play live" enrichment, not event source |
| PredictHQ | Free plan: 2 saved locations (docs.predicthq.com/getting-started/guides/using-the-api-with-the-free-plan) | Paid ~US$500+ (third-party, conflicting) | Demand-intelligence oriented; concert coverage and terms UNVERIFIED |
| SerpApi (Google Events) | Self-serve | Free 250 searches/month; Starter $25/mo for 1,000 https://serpapi.com/pricing | Scraped Google data; legal risk sits with provider ("Legal Shield" paid feature); caching/AI terms UNVERIFIED. Possible long-tail fallback |
| Resident Advisor | No official public API found; only unofficial GraphQL/scrapers | - | Do not use without permission |
| DICE, AXS | No developer/partner API found in search | - | UNVERIFIED |

### Deduplication across sources
Normalise to canonical Artist (MBID where known, else normalised name), Venue, and Date. Match key: (date, venue_id) first; fall back to (date, geohash of venue ~150 m, fuzzy headliner match). Match venues by name similarity plus distance; MusicBrainz places are an optional canonical venue list. Keep per-source ticket links as offers on one event record; prefer the Ticketmaster URL when it carries affiliate tracking. Respect source caching limits when persisting (store IDs plus short-TTL cache, not a permanent mirror, for Ticketmaster).

---

## 5. Geocoding and place resolution

| Provider | Free limit | Caching / storage | Notes |
|---|---|---|---|
| Nominatim (public OSM) | 1 req/s absolute cap per app; no autocomplete; bulk discouraged | Cache required; ODbL attribution https://operations.osmfoundation.org/policies/nominatim/ | Fine for one-off city lookups from a submitted form, behind a cache |
| Photon (komoot) | No numeric limit; "extensive usage will be throttled"; no availability guarantee https://photon.komoot.io/ | Licence/commercial use not stated; check repo | Supports search-as-you-type better than Nominatim; self-hostable (UNVERIFIED effort) |
| Geoapify | Free 3,000 credits/day, 5 rps, "limited commercial use" https://geoapify.com/pricing (via search) | Official caching terms not found; third party says permitted with attribution (UNVERIFIED) | Best hosted free choice for autocomplete |
| Mapbox | Temporary geocoding free to ~100k requests/month (third-party); Permanent geocoding has no free tier, about $5/1,000 | Temporary results may not be stored or cached; Permanent allows storage (third-party summaries, official terms not read) | Avoid unless a map is also needed |
| Google Places | Place IDs may be stored indefinitely; attribution/logo rules https://developers.google.com/maps/documentation/places/web-service/policies | Lat/lng caching rules and free quota not verified: UNVERIFIED | Paid; unnecessary here |

Recommendation: user picks a place via autocomplete (Geoapify or self-hosted Photon), store the returned lat/long/city in the request, and send TM `geoPoint`. Remove the LLM from geocoding.
