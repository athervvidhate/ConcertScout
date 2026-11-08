# Fluid Search study

A high-fidelity study of the home page and the whole Search journey. Open `index.html` in a browser (it loads GSAP and the Ticket photos from the web). `journey.mp4` is a 42-second recording. The study bar switches light and dark mode.

## Why it replaced the scene studies

The owner rejected the earlier drawn-scene studies (since deleted). Two lessons:

1. **Drawn SVG scenery reads as clip art.** Concert Scout already holds the real material: source photographs of the Artists playing each Concert. This study uses only those.
2. **Responsiveness comes from the product, not the pointer.** Nothing here follows the cursor. Everything that moves reacts to what the person did or what the agent is doing.

## Data

`data.js` holds eight real Searches replayed offline from the eval Snapshots captured on 2026-11-07, with every `status`, `interpreted`, `candidates` and `poster` event as the pipeline produced it. Between them they cover 0, 1, 2, 3, 4 and 8 results. Concert facts and photographs come from Ticketmaster; the "Why it fits" text is the ranker's. Nothing on the page is invented. A missing time or price is left out. Typing anything other than the eight replayed Searches offers them instead of faking results.

The dark bar at the bottom is a study control, not product UI: it jumps to the Search that found 8, 4, 3, 2, 1 or 0 Concerts.

## Decisions so far

- **Home strip.** Visitors without Spotify see the top picks of the home example Searches. The daily warm-up job runs those Searches every night and caches them, so the strip and a click on any example never trigger a paid Search, and the dates are always upcoming. A visitor with Spotify connected sees their own Artists playing near them instead. No place is ever inferred from an IP address.
- **Views.** Grid and List only, switched by two icons (labelled for screen readers and on hover). The one-by-one deck was dropped.
- **Home sections.** The search box and pitch, the labelled photo strip, How a Search works, Make it yours, and the footer. The "facts come from the listing" section was dropped.

## The page

**Surface.** Flat paper, solid surfaces, hairline borders and one small shadow. No blurred colour blobs, grain or frosted glass. Colour comes from the photographs; coral is kept for actions and the place in the headline.

**How a Search works.** One real Search ("Something like Khruangbin in Chicago") plays in three panels while the section is on screen: the words become Artist and Place chips, the 40 Artists with Concerts in Chicago appear, then the three picks stay dark and arrive with their reason. About two seconds after the last step, everything in the panels fades and lifts away together and the loop starts again. Each panel holds the height of its finished state, measured at the current width (steps side by side share the tallest), so the green band never changes size while the panels fill and empty. It stops when scrolled away.

**Results by count.**

| Concerts | Layout | Below it |
| --- | --- | --- |
| 0 | "Nothing here fits", how many Artists play there, and three ways forward | Every Artist that plays there, by name |
| 1 | The Ticket is the Poster: photo beside the facts, reason, Get tickets and Save | The other Artists that play there |
| 2 | Two tall halves with reasons | The other Artists, 18 then "Show N more" |
| 3 | One large card and two stacked | Same |
| 4 | Four halves | none |
| 5–8 | Large card, two stacked, then thirds and halves | none |

**List view.** A running order: date, lead Artist, the rest of the bill, venue, time, reason, photo. Switching fades the current view out and raises the new one card by card. Nothing is scaled, and no empty placeholder boxes show.

## What moves

- **Rolling example Search** and the strip that widens the Artists each found.
- **Search button** turns into a coral "Search" once there is text.
- **The Search box** travels to the top on submit and back to the middle from the brand.
- **Status** swaps icon and line at each real step.
- **Narrowing.** Candidate names stream in, the picks darken, the rest fade.
- **Name into title.** Each picked name travels as one pill: the dark chip and its text move together. Right as it leaves, the text hands over from the pill's type to the title's on the same left edge and centre line; the pill grows to the title's size and measure, and its background fades over the last stretch, leaving the title where the card sets it.
- **Ticket open.** A copy of the card photo travels above everything to the Ticket's photo slot, keeping its crop as its box changes. When it lands, the sheet appears clipped to the photo and opens out, and the details slide in from behind the photo. Closing reverses it: the details fold back behind the photo, then the photo returns to the card's visible photo frame and lands at exactly its size.
- **Saving** fills from the click and rolls the nav count.

Reduced motion shows every end state immediately and does not loop the demo.

## Palette: Moss

Decided November 7, 2026, after three rounds of palette studies: **Moss**, with a light and a dark mode. No cream. The light page is a green-tinted white with a pine How band and deep coral actions; the dark page is green-black with a lifted pine band and coral actions. Dark mode follows the system setting; the sun/moon button in the study bar switches it, and `?mode=dark` links to it.

Colours are role tokens in `style.css` (`--bg`, `--surface`, `--ink`, `--band`, `--accent`, `--on-accent`, `--soft`, `--label` and so on). Light sits on `:root`, dark on `:root[data-mode=dark]`; lines, shadows and chip tints are mixed from the tokens. Both modes meet 4.5:1 for body text, band text and button text.

## Validation

`node docs/mocks/fluid-search/evidence/check.cjs` runs at 1440×900 and 390×844, with and without reduced motion. It checks:

- the removed sections are gone
- the demo reaches its third step and, with motion, loops back to an empty start by itself, while the How band keeps one height and no panel clips its content
- every study Search reaches its results with the right number of Concerts, with no leftover name copies
- Grid and List show the same Concerts through the two icon buttons
- the Ticket opens on screen with its photo in place and no leftover photo copy, Save in it updates the nav count, and Escape closes it, restores the card photo at the card's exact size with no leftover scale, and returns focus to the card
- an unknown Search offers the replayed ones
- no sideways scroll and no errors

It passes. Frame captures of the name morph and of the Ticket opening and closing at 1280 and 390 were inspected. `evidence/*.png` are final states. Not verified: real-device frame rate, screen-reader review, and production integration (the real app streams these events over SSE, which the replay imitates with fixed delays).

## Not in scope yet

Saved Concerts and Your Taste pages, Spotify, the Artist panel, editing a chip to refine a Search, the Elsewhere board, and the approved Poster choreography in `docs/specs/04-interface.md`, which this study departs from on purpose.
