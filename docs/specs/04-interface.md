# Interface

The approved [Fluid Search study](../mocks/fluid-search/README.md) supplies the layouts and motion. Moss light and dark replace the orange field, rotating sun, coloured Tickets and one-by-one deck. This spec governs the live application; study-only controls do not ship.

## Tokens, type and identity

Use the study's role tokens: light paper `#f3f5f2`, surface `#ffffff`, ink `#12261f`, pine band `#12352b`, coral action `#c4461f`. Dark paper is `#0d1915`, surface `#14241f`, ink `#e8f0eb`, pine band `#1f4a3b`, coral action `#ff7449`. Derive hairlines from ink. Flat surfaces and a small shadow; photographs provide colour. Gradients may support photo legibility, never decorate the page.

Anton is display type and Bricolage Grotesque is UI/body type, loaded with `next/font/local`. Dates and prices use tabular numbers. The ticket/compass identity has standalone outlined SVG variants for light, dark and pine surfaces; header colour follows the page before paint. The adaptive SVG favicon and PNG/ICO renditions use the symbol alone.

Follow the system colour scheme on first visit. The header menu switches light/dark and remembers the choice when storage permits. Failure to persist must not prevent switching for the visit.

## Home

The header carries the logo and a menu with Saved Concerts, Your Taste, theme and optional account controls. The logo returns to the resting home page. Search replaces the home sections; navigation never submits a Search.

The headline rolls through example ways to Search. The main Search box has one input, an explicit location button and Search action. The input rotates the three examples while it is empty on home, then stays blank after a Search. Reduced motion uses static text. Examples also appear as buttons below the box.

A labelled photo strip shows cached public example Posters, refreshed by the authenticated nightly warm job. Neither a visit nor an example click can make a paid Search. A cache miss leaves the strip out and puts the example words in the input with an explanation. A visitor may explicitly submit those words as an ordinary Search. Expired source dates stay out. Spotify-connected visitors see their own separate shelf instead of the public strip.

How a Search works replays one actual cached Search in three panels: understood words, candidates, then picks. Content remains in layout while it fades, keeping each panel's finished height. Animation stops out of view; reduced motion displays the finished state. Without cached data it shows the three explanations without inventing a demo. Make it yours offers location and Taste; it retires once Spotify is connected. The footer links Privacy and the owner.

Location is requested only on an explicit button press. Forget my location deletes the stored coordinates. Typed places win over shared coordinates, and no place comes from an IP address.

## Working view

The live SSE stream drives status, understood Artist/sound/place/date context and the candidate cloud. Candidate names arrive from `candidates`, never invented or taken from Spotify. Show up to 40 shortlisted Artist names while ranking. On `poster`, picked names become the Concert titles through Motion shared layout. There is no percentage progress, artificial network wait or legacy multi-second loader sequence. An empty Poster removes the cloud and offers useful changes.

## Poster and Ticket

Grid and List use two icon buttons with accessible names and pressed states. Both show exactly the same Recommendations in rank order. Grid follows the count: 1 a solo Ticket, 2 halves, 3 a large pick with two stacked, 4 halves, 5–8 a large pick, stacked picks, then thirds/halves. Phones stack the Concerts. List shows date, Artist, rest of source title, venue, time, reason and photo where reported. At three or fewer picks, list the other candidate Artists, initially 18 with a Show more button.

A Concert opens an accessible Ticket dialog. Motion shares the source photo's layout between its Poster frame and the dialog; closing returns it to the Poster. The details use the same source facts as Saved Concerts: Artist panel, first-Ticket hint, date and venue time zone, reason, price only if known, next presale before general sale, other dates grouped by venue, and the source ticket link. A single Recommendation also exposes its Ticket directly on the Poster.

The owner chose Save only on November 7, 2026. Remove Skip and drag, the deck, and its end panel. Save confirms device/account storage without closing or advancing. A saved check and text work without colour alone; failed storage never claims success. Account failure rolls back the optimistic save and permits retry. Escape, close and backdrop restore focus to the opening Concert. The Artist panel remains a nested accessible dialog.

List switching fades the old view then raises the new Concerts with a short stagger. Reduced motion shows end states immediately. Only transforms and opacity animate continuously; there are no pointer-following effects. Keep touch controls at least 44px. Verify 390px and 1280px widths, both themes, reduced motion, keyboard focus and no horizontal document overflow. Physical-device frame rate and screen-reader acceptance are separate from automated Chromium checks.

## Empty, errors and existing features

An empty Poster says Nothing here fits. Offer a Search over the next three months using the understood Taste/place, a worldwide Search when the API supports a named Artist, and editing the Search. Actions that submit still require a fresh bot token. Elsewhere remains a source-only board for an empty place/Taste Search. It never becomes a model-ranked Poster.

Keep Turnstile, visitor/spend limits, Search-off 503, actionable errors and truncated-stream retry. The API pipeline and source-fact assembly remain the authority. Keep Spotify exact-name matching, its separate data path and hide/paging controls; Taste imports; optional accounts and synced saves; Privacy and credits.

## Artist panel, hint and reports

An Artist's name opens public Last.fm facts and a Spotify page/search link without a model. Missing facts stay out; if Last.fm knows nothing, say so and keep the Spotify link. The first-Ticket hint disappears after opening a panel or saving and stays dismissed on that device.

After a Search, Tell us opens a note. Reports use Resend and preserve existing limits and configuration. They include Search, interpretation, error and Poster facts, never location coordinates or connected Spotify data. Privacy opens in a separate tab so the active Search survives.
