# Broad Concert discovery: APIs, venue ingestion and fast Searches

Research date: November 7, 2026. This supersedes the prioritization in [the earlier South Asian coverage note](2026-11-07-ticketing-coverage-south-asian.md). Bollywood was an example of a coverage gap; the objective is broad US Concert discovery across sellers, supplemented by sources for particular scenes and eventually other countries.

Research and live read-only probes only. No app, hosting, credentials or product specs were changed. No accounts, subscriptions, feed applications or outreach were initiated.

## Recommended implementation

Build a shared Concert pool from **broad APIs plus venue and scene sources**, refreshed outside the Search request. Retain Ticketmaster, evaluate JamBase as the first broad additional feed, and add a small number of venue adapters selected by measured omissions. Pursue See Tickets' documented marketplace feed alongside that work. Use Artist tour calendars to discover additional venue/seller combinations rather than assuming every Artist uses one seller everywhere.

The source of a Concert and the seller at checkout are different. A Concert listed on Ticketmaster can already link to TicketWeb or another partner. Conversely, a venue's own ticketing can be absent from Ticketmaster's Discovery API. Counting external links as omissions would give the wrong answer.

## What the live probes established

### Ticketmaster versus actual venue calendars

Used the existing app's Ticketmaster client and parser with the configured key, without printing credentials or making model calls. Seven successful, read-only Discovery API requests used California (`countryCode=US`, `stateCode=CA`), November 7–22 inclusive, page zero, size 200, date order. All totals were below a page. The first four used the product's Music filter; follow-up Artist queries omitted it to check whether classification caused the omissions. Earlier sandbox-blocked attempts failed with `ConnectError`; they are not empty-source results. Local Redis was unavailable, so the client's normal local pacing fallback applied. No service was started or stopped.

| Venue/calendar evidence | Ticketmaster observation | Interpretation |
|---|---|---|
| [JSTJR, SOMA, Nov 14](https://www.somasandiego.com/event/jstjr/) | `keyword=SOMA` returned JSTJR with `https://www.ticketweb.com/event/jstjr-soma-mainstage-tickets/14285814`. | Already discoverable through Ticketmaster, despite checkout elsewhere. The venue's short ticket link resolves to that same TicketWeb URL. |
| [Father Of Peace, SOMA, Nov 8](https://www.somasandiego.com/) | Returned both a Ticketmaster record and a TicketWeb record for SOMA/Sidestage. | Additional source rows need deduplication; they do not necessarily represent additional Concerts. |
| [Isaiah Rashad, SOMA calendar](https://www.somasandiego.com/) | The calendar says Nov 19. API returned a Nov 17 record and two Nov 19 records; the latter URLs differ only by a seller query parameter. | A concrete stale-date/duplicate case, requiring status and rescheduling reconciliation. Do not automatically recommend both dates. |
| [Hit The Lights, Lodge Room, Nov 8](https://www.lodgeroomhlp.com/shows/hit-the-lights/) | Venue-keyword query returned only Bayonne on Nov 21. Separate `keyword=Hit The Lights`, without Music filter, returned an Anaheim Concert on Nov 7 but no Nov 8 Lodge Room date. | A specific venue date missing from these Discovery queries, while another date for the same Artist exists. |
| [Natural Child, Lodge Room, Nov 13 and 14](https://www.lodgeroomhlp.com/) | Separate `keyword=Natural Child`, without Music filter, returned Rickshaw Stop on Nov 20 but neither Lodge Room date. | Another specific gap that a venue adapter could recover. |
| [King Buffalo, Lodge Room, Nov 7](https://www.lodgeroomhlp.com/) | Separate `keyword=King Buffalo`, without Music filter, returned two Belly Up records for Nov 9, but no Lodge Room date. | Supports the same gap pattern, although the research-day performance may already have started by a later reproduction. |

`keyword=Adriatique` and `keyword=Moby` with Music filtering also returned no records. Those alone are not conclusive omissions: Artist/title/Lineup matching and festival representation need checking against the exact performance. The [19hz SoCal calendar](https://19hz.info/eventlisting_LosAngeles.php) lists these performers, but this is only a lead.

These are bounded query observations, not proof that a Concert is absent from every Ticketmaster system, nor a measured US-wide recall percentage. They establish that broadening ingestion can add real venue dates, and that seller diversity alone does not measure coverage.

### Feasibility of venue extraction

Fetched the public HTML of [SOMA's full calendar](https://www.somasandiego.com/events/) and [Lodge Room's homepage](https://www.lodgeroomhlp.com/) successfully with HTTP 200. Both contain listings in the initial response; a browser renderer is unnecessary for those tested pages.

- SOMA exposes separate date fields, titles, venue-page links, status labels and ticket links in ordinary HTML. The tested JSTJR detail page's JSON-LD describes WebPage/Organization entities, **not an Event**: finding `application/ld+json` does not mean it contains Concert records.
- Lodge Room embeds structured `eventObjects.push({...})` records containing its local ID, date, headliner, supporting Artists, venue, image, canonical page and doors time. It also renders visible Concert information. This is an extraction opportunity, not a documented or versioned public API. Parse only validated data literals; never execute page scripts. Its visible calendar includes non-music listings too.
- [Zebulon's page](https://zebulon.la/) yielded little listing text in the web reader. That is not proof it needs browser rendering; inspect its actual HTML/feed before choosing a renderer.

Production crawl/display permission, freshness and parser stability remain unverified for these venue pages. A proof that HTML is extractable is distinct from an approved recurring integration.

## Best source options

| Source/path | Verified access and fit | Decision |
|---|---|---|
| **Ticketmaster Discovery** | [Docs](https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/) say all its supported source platforms are returned by default, including Universe and FrontGate. Live probes also returned TicketWeb links. | Keep as baseline. Do not create redundant connectors merely because checkout is external. |
| **JamBase Data** | [Search](https://data.jambase.com/api/docs/search) supports dates/places plus Artist, venue and title filters; [bulk sync](https://data.jambase.com/api/docs/bulk-ingest) documents local ingestion and modified-record polling. [Pricing](https://data.jambase.com/pricing): non-commercial Developer, 1,000 included monthly calls, then $0.05/call, six-month future window. | First broad API spike. Test the missing venue dates above before adopting. [Terms](https://data.jambase.com/legal/developer-terms) explicitly allow hobby/portfolio apps and a synchronized local copy, while restricting redistribution/competing data products. Confirm recommendation-app display fit, not raw dataset resale. Set a hard quota cap. |
| **Ticket Fairy** | [Public listing API](https://www.ticketfairy.com/developers), no key, pagination and country/date filters; previous research confirmed live HTTP 200. [19hz](https://19hz.info/eventlisting_LosAngeles.php) links a real SoCal bass Concert to it. | Second accessible API candidate. Keyword relevance needs validation; the previous Bollywood probe returned unrelated records. No city/radius filter should be invented: use documented filters and validate venue coordinates locally. |
| **See Tickets / Eventim US** | [Official affiliate feed documentation](https://clients.seetickets.us/hc/en-us/articles/18890091910939-Affiliates-Network) describes event ingestion for external marketplaces, venue filters and pagination. Team-provided credentials required; feed scope follows eligible/approved public active listings. It documents midnight festival placeholders and misleading minimum prices from parking. | Concrete partnership path, stronger evidence than merely finding an API logo. Ask about non-affiliate display-only access: the current product has no affiliate links. Do not silently introduce commissions/tracking or assume complete inventory. |
| **AXS** | No suitable self-serve discovery API verified. [US terms](https://www.axs.com/legal/terms_of_use.html) restrict automated indexing/extraction and AI/automated-decision use without applicable consent. | Seek discovery/feed permission or ingest independently published venue facts under that source's rights. Do not make a recurring AXS scraper the default portfolio dependency. Keep source provenance so upstream restrictions can be enforced. |
| **Eventbrite** | [Official announcement](https://groups.google.com/g/eventbrite-api/c/FT2MsDswdrA) discontinued global event search; organizer/event retrieval and distribution access are separate routes. [Current terms](https://www.eventbrite.co.uk/help/en-au/articles/251210/eventbrite-terms-of-service/) prohibit scraping. | Organizer-authorized API feeds or a distribution arrangement; independent venue/promoter calendars can still link to Eventbrite checkout. Consumer-site internal JSON is not equivalent to supported API access. |
| **DICE, RA, Tixr, Etix** | DICE's documented [Ticket Holders API](https://partners-endpoint.dice.fm/graphql/docs/index.html) concerns partner operations; [Tixr integrations](https://creators.tixr.com/products/integrations) and [Etix partner terms](https://www.etix.com/ticket/online3/apiPartnerTerms.jsp) establish integration paths but not open discovery. RA has public scene listings, not a verified open discovery contract here. | Feed inquiries and venue-level gap filling. Avoid equating an anonymously reachable internal endpoint with a stable licensed catalog API. |
| **Showpass** | [Public organization listing docs](https://dev.showpass.com/api/public-api-event-list-by-organization/) support one/multiple organization IDs, date filters, paging; domain whitelisting required. | Useful venue/organizer adapter with cooperation; not an assumed unrestricted platform-wide feed. |
| **Songkick / Bandsintown** | [Songkick](https://www.songkick.com/developer) excludes hobby access; [Bandsintown](https://help.artists.bandsintown.com/en/articles/7053475-what-is-the-bandsintown-api) requires review for platforms and excludes personal/educational requests. | Do not build the first version around approval that current policies exclude. |
| **Tickets.dev** | Vendor [API reference](https://tickets.dev/docs) advertises a free keyed unified discovery catalog, with marketplace links; its current indexed sources do **not** list AXS, DICE or Eventbrite. | Potential low-cost evaluation, not a fix for those three gaps. Live access, coverage and downstream display rights not tested. Vendor documentation is evidence of its offer, not proof of completeness or upstream authorization. |
| **TicketsData** | Vendor [docs](https://ticketsdata.com/docs) advertise AXS/DICE/Eventbrite among inventory sources. Its [pricing](https://ticketsdata.com/pricing) starts at $499/month; AXS is on Pro at $2,499/month. Per-performer/organizer discovery differs from bulk catalog access. | Out of current hobby budget. Paying for a JSON wrapper does not establish a broad discovery feed or downstream rights. |
| **Data Thistle / PredictHQ** | [Data Thistle](https://www.datathistle.com/what-we-do/for-publishers/) supplies publishing APIs/feeds, particularly worth evaluating for UK expansion. [PredictHQ](https://docs.predicthq.com/api/events/search-events) supports global location/date/category search but subscription scope can silently omit territory/date ranges. | Paid expansion candidates, not first choices for current US music budget. Verify ticket links/Lineups and entitlement before treating either as equivalent to a music discovery feed. |

## Sources for particular scenes

Start with broad feeds, then add the sources with demonstrated unique Concerts for a Region or musical scene. These are candidates, not promises of immediately usable APIs.

| Scene | Sources and integration implications |
|---|---|
| Electronic, clubs, experimental dance | [19hz](https://19hz.info/) and [its source list](https://19hz.info/sources.html), RA, Restless Nites, Shotgun and promoter calendars. 19hz is volunteer-curated and spans multiple sellers, with tags and venue/organizer links. Ask for a feed/reuse arrangement; a source list also helps select original venue adapters. |
| Electronic API | [Edmtrain docs](https://edmtrain.com/api-documentation) offer location/Artist/venue/date search, but [developer policy](https://edmtrain.com/developer-api) explicitly prohibits combining its Concerts with other sources into a competing discovery service. **Requires an exception/agreement for this design**, despite technically suitable endpoints. |
| Indie, rock, punk, alternative | [Oh My Rockness](https://www.ohmyrockness.com/pages/about-us) hand-curates NYC, Chicago and LA. No open feed verified; pursue permission. Venue calendars such as Lodge Room are a more targeted initial adapter with observed omissions. |
| Jazz, blues, intimate rooms | [InstantSeats](https://www.instantseats.com/) includes jazz-room listings; supplement club and presenter calendars. No broad discovery API verified here. Model multiple sets on one night as distinct performances. |
| Classical/opera/chamber | Orchestra/hall calendars first. [Classical Concert Map API](https://www.classicalconcertmap.com/api-docs/) is free/no-key, but acknowledges model-extracted facts, unstable Concert IDs and unknown-time placeholders. Treat it as a discovery lead and validate facts against presenters before production, consistent with ADR 0002. |
| Regional/cultural/linguistic scenes | Sulekha and cultural presenters from the earlier note, plus analogous local promoters. Cultural relevance is a source-selection dimension rather than a restriction on the whole product. |

For non-US coverage, preserve the same architecture: validate local seller/venue feeds region by region. Ticketmaster and JamBase can be evaluated internationally; Skiddle, Data Thistle, DryTickets, BookMyShow/District and Platinumlist remain regional leads, with access qualifications in the earlier report. An API's global availability does not establish global completeness.

## Keep Searches fast

1. **Scheduled ingestion:** fetch source pages or changes; normalize, validate and deduplicate; publish a complete source generation only after all pages succeed. Retain the prior successful generation on a failed refresh. Apply cancellations/removals, not only new records. JamBase explicitly documents [delta updates](https://data.jambase.com/api/docs/bulk-ingest) and [deletion records](https://data.jambase.com/api/docs/deleted-items).
2. **Warm Search:** read scoped Concert pools from Redis, merge candidates, then run existing matching/shortlist/ranking once on the combined pool. The visitor does not wait for a crawl or one model call per source.
3. **Cold Search:** query supported APIs concurrently with per-source deadlines and a shared overall deadline. Serve a permitted recent snapshot if available; report partial coverage if a source fails. Queue missing refreshes. No unbounded scraper fallback inside a Search. A named Artist can trigger a bounded API lookup; avoid live browsing an arbitrary Artist website on every request.
4. **Control work:** per-domain concurrency, provider quotas, conditional HTTP requests when supported, shared locks for identical refreshes, source-specific freshness limits and a crawl budget. Refresh frequency follows source terms and observed change patterns. Status checks for imminent performances can be prioritized separately from whole-catalog refreshes.

This is an architecture recommendation, **not a measured latency improvement**. Measure cold/warm pool time and total Search p50/p95, both before and after adding a source. Include failures, additional Artist enrichment and shortlist recall: a fast fetch can still lose value if new Artists overwhelm matching or the top-40 cutoff.

For initial authorized page adapters, use async HTTP plus deterministic JSON-LD/HTML parsing. Use a browser renderer only for pages demonstrably requiring JavaScript, in a separate ingestion worker. Browser pools, retries and HTML drift can make crawling unpredictable; keep them away from the Search deadline. Identify the application/repo in the User-Agent, not a personal email. Honor each source's applicable crawl and display arrangement; robots.txt is an operational signal, not itself a republication license.

## Concrete changes in this repo

The existing `sources/ticketmaster.py` already returns typed Concerts and the `pool.py` cache shares geographic/month scopes, but both the pool and warming code are Ticketmaster-specific. `Concert.id` currently holds a vendor ID; `url` holds one ticket link, and source provenance/status/coordinates are absent. The Recommendation docstring also assumes other dates share a source.

The first implementation slice should:

- Add **one** source adapter and source-aware pool collection; keep adapters small rather than creating a generalized scraping framework.
- Namespace source IDs and cache keys; keep raw source records/provenance and last verification separately from the normalized Concert used for ranking.
- Add a stable canonical identity/alias mapping for cross-source Concerts; retain all source records and seller links. Normalize harmless URL tracking variations without stripping meaningful ticket tokens. Match venue + date + Lineup conservatively; time distinguishes two sets. Reschedules need explicit linkage rather than title similarity alone.
- Keep the existing Redis pool approach for bounded metro experiments; do not add another database solely for this spike. If ongoing mirrors, stable identities and nationwide crawl state outgrow it, choose durable storage as a separate measured decision. Do not treat six-hour cache expiry as a deletion signal.
- Preserve missing facts, date/time precision, territory and currency. Separate discovery provenance from checkout seller. Keep scraped descriptions out of model instructions; no fact generation by a model.
- Add contract cases at adapter/pool boundaries for real captured payloads, duplicate links, source failure, refresh atomicity, cancellation, rescheduling, missing fields and identity collisions. Confirm the Poster can still surface added Concerts rather than only proving they exist in storage.

This is a proposal, not an implementation or ADR. The product's Ticketmaster-only scope must be updated as part of an authorized feature slice. Research artifacts stay separate from other agents' UI/deployment changes.

## Measure what Ticketmaster misses

Create a reproducible coverage audit for the **raw pool and final Poster separately**:

- Fix a Region, dates, retrieval time, API parameters and independent venue/Artist reference set. Begin with SOMA and Lodge Room, then sample additional genres, room sizes and ticket sellers in LA, San Diego and other US metros. The live probe above is useful evidence but not a representative sample.
- Snapshot the source calendar and raw Ticketmaster response. Search exact venue and Artist names; use broader filters when needed. Label `present`, `missing from bounded API lookups`, `duplicate`, `stale/conflicting`, `out of scope`, and `unresolved` rather than collapsing every mismatch into “missing.”
- Distinguish vendor coverage from app exclusions: paging/date/geographic scope, missing Lineup identity, matching, shortlist and ranker can each lose a Concert that the vendor already has.
- For each added source, record newly verified canonical Concerts, duplicates, conflicts, age of verification, request/crawl cost and whether the final Poster recovers relevant reference Concerts. Compare against the independently verified reference set, not the union of whichever feeds were easiest to call.

**First build:** an offline coverage-audit command with captured records, followed by one JamBase adapter if it recovers useful dates. Also resolve access questions for See Tickets and the most valuable venue/scene sources. If JamBase fails to recover the observed Lodge Room omissions, prefer the venue adapter over adding another broad API on faith.
