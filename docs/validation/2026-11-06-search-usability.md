# Search usability validation — 2026-11-06

The home layout changes already in progress were preserved: one Search box, a location button, a Your Taste side panel, and external Ticket links opening a new tab. The unused `/places` endpoint and second place input are removed. Local Search allowance is configurable through `SEARCHES_PER_HOUR`.

## Reproduced and fixed

Before the fix, live `UKG in SF` and `UKG in LA` returned `place_not_found`; `techno in the bay` searched the wrong locality; Texas was searched as a circle around its center. Regression tests reproduced unchanged SF, separate alias caches, and missing state boundary fields before implementation.

Common place aliases are expanded only in the extracted place field. Common genre aliases normalize both interpreted Taste and source tags. The existing interpreter expands other familiar shorthand; no extra model call is added. Unknown names and explicit qualifiers stay intact. This is a maintained small alias map, not a comprehensive city dataset. Broad regions such as the Bay and DMV currently use the ordinary 50-mile city radius. State boundary filtering covers Geoapify state results in the US and Canada; multiple separate locations in one Search are not implemented.

Geoapify documents `result_type`, `country_code`, and `state_code` in its [geocoding contract](https://apidocs.geoapify.com/docs/geocoding/). Ticketmaster exposes `countryCode` and `stateCode` in its [Discovery API explorer](https://developer.ticketmaster.com/api-explorer/). MusicBrainz identifies [UK garage](https://musicbrainz.org/genre/95c57cd7-7fb8-4405-ade1-775c2d27e54e) as a genre. No external dataset is downloaded at runtime.

## Evidence

- `make check`: 237 backend tests and 80 frontend tests passed, including lint and type checks.
- `npm run build -- --webpack`: passed. Next emits its existing Big Shoulders font override warning; the font loads in the browser.
- Live pipeline: `UKG in SF` returned Sammy Virji; `UKG in LA` resolved Los Angeles and returned three Recommendations; `techno in the bay` resolved San Francisco; `indie rock in Texas next weekend` found 98 Concerts and returned eight Recommendations; `UKG in London` returned eight. These are smoke checks, not human relevance judgments. Some broad electronic picks remain a judged-evaluation concern.
- Actual browser UI at 1280px: `UKG in SF` returned Sammy Virji with its source venue, date, time and Ticket link. The smaller reveal contained eight names, with one final pick.
- At 390px, `document.documentElement.scrollWidth === innerWidth === 390`. The single-pick Poster and Ticket fit without horizontal overflow.
- Actual browser empty Search: `UKG in SF on January 1, 2099`. A MutationObserver recorded zero visible wall names throughout; final state contained no wall, no Poster names, and the explanatory empty message.
- Home snapshot observed the placeholder rotating through the examples. The rotation pauses on focus, entered text and active Searches; reduced motion keeps a static example.

The candidate count is labeled Concerts considered, rather than close matches. The candidate event remains available for evaluation, but the UI waits for qualified picks before revealing names, caps the sample proportionally, and collapses spare space for up to three picks.
