# Underground Venues & Curated Promoters

Ticketmaster and JamBase miss many underground electronic, club, and DIY rooms. This slice adds two local-first supply sources that keep Search latency flat and preserve [ADR 0002](../adr/0002-facts-never-pass-through-the-llm.md).

## 1. Curated Venue Calendars (`schema.org/MusicEvent`)

An explicit registry (`api/concert_scout/underground_registry.py`) lists flagship underground rooms with canonical venue name, city, state, coordinates, IANA time zone, and HTTPS calendar URL (Nowadays, Public Records, Elsewhere, Smartbar, Marble Bar, 1015 Folsom, Basement, Good Room).

- `api/concert_scout/sources/jsonld_venues.py` fetches each calendar through `sources.http.make_client` with `USER_AGENT` (never a personal email), strict timeouts, HTTPS-only URLs, and zero retry storms.
- It extracts `schema.org/MusicEvent` nodes from `<script type="application/ld+json">` tags (single object, list, or `@graph`), resolves relative event and image URLs to HTTPS, converts `startDate` into the venue's local date and time, drops cancelled/postponed/moved-online listings, records `offers` price only when currency is reported, and marks `SoldOut` offers as `sold_out=True`.
- Extracted `performer` names are confirmed via `musicbrainz.confirm` before joining `Concert.artists`. Unconfirmed names stay out of `artists` and are never invented from titles. Confirmed `venue_calendar` Concerts participate normally in Artist matching and co-billing.

## 2. Curated Eventbrite Promoters (Non-Lineup Display)

Eventbrite permanently disabled global search, and organizer listings carry no structured Artist Lineups (`artists=[]`) while titles often name absent Artists (such as unofficial afterparties).

- `api/concert_scout/sources/eventbrite.py` reads only explicitly configured organizer IDs (`EVENTBRITE_ORGANIZER_IDS` with `EVENTBRITE_TOKEN`) via `sources.http.make_client` (zero retries, tokens out of INFO logs).
- Every harvested Eventbrite Concert keeps `source="eventbrite"`, `artists=[]`, and `sold_out` strictly from `ticket_availability.is_sold_out`. Title parsing never promotes Eventbrite titles into `artists`.

## 3. Local Redis Storage & Authenticated Sync

Searches never scrape venue websites or call Eventbrite live.

- `api/concert_scout/underground.py` stores harvested listings in cell-by-month Redis hashes (`underground:cell:{cell}:{YYYY-MM}`, `underground:where`, `underground:cells`, `underground:state:{region}`, `underground:source:{source_key}`) with automatic post-month expiry, mirroring `catalog.py`.
- `POST /sync-underground` requires `Authorization: Bearer <CRON_SECRET>` (identical to `/sync`), acquires `underground:sync-lock`, harvests venue calendars with bounded concurrency and polite pacing, harvests configured Eventbrite organizers, prunes expired `underground:where` entries, and returns safe step summaries.
- `pool.find_concerts` reads `underground.concerts_near` alongside `catalog.concerts_near` (<5 ms local Redis read), and `pool.find_concert` resolves `venue:*` and `eventbrite:*` IDs for Saved Concerts.

## 4. Deduplication & UI Badges

- `pool.merge_sources` keeps primary listings (Ticketmaster, then JamBase) over duplicates. Confirmed `venue_calendar` Concerts deduplicate by date, shared Artist, distinctive venue word, and nearby set time. Non-Lineup Concerts (`artists=[]`) deduplicate conservatively only on the same date, shared distinctive venue word, nearby set time, and matching normalized title (never collapsing unrelated nights or afterparties).
- `frontend/components/underground-badge.tsx` renders Moss-palette pills on Poster cards and Tickets: `"Underground room"` for `venue_calendar`, `"Curated promoter"` for `eventbrite`, and `"Sold out"` when `sold_out === true`. Standard Ticketmaster/JamBase Tickets render nothing extra and keep their fixed height.
