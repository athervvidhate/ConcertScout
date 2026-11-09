# Product

## Home

The home page shows Concerts near the visitor without any LLM call, so it costs nothing and loads at once. The visitor types a place in the main Search box or allows browser location. We never infer a place from an IP address.

A single search box sits at the top. It takes plain text such as "Something like Khruangbin in Chicago, next two weekends".

## Search

A Search needs a Taste, a place, or both. Dates are optional.

| Input | Behavior |
|---|---|
| Taste and place | Rank Concerts near the place against the Taste |
| Place only | Show notable Concerts near the place, soonest first |
| Taste only | Look up the seed Artists and top similar Artists directly, then show their nearest Concerts anywhere |
| No dates | Search the next 6 months, plus every listed Concert by a named Artist |
| Neither Taste nor place | Ask for one, inline, with no LLM ranking call |

Typed Taste beats imported Taste when they conflict. An imported Taste fills in only what the text leaves open.

The page streams real progress. See the loader in [04-interface](04-interface.md).

## Poster

A Poster shows up to 8 Recommendations in Grid or List view. Grid follows the number of picks: a solo Ticket, two halves, a large pick and two stacked, four halves, or a larger composition for five to eight. It never pads with weak picks.

Each Artist appears once. Their other dates sit behind "more dates" on the Ticket. Clicking a Concert opens its Ticket dialog; one pick also shows its Ticket directly on the Poster. A saved Concert carries a check and a "Saved" label. For three or fewer picks, the other shortlisted Artists appear under "Also playing, not picked".

If nothing qualifies, the page says so and offers the nearest useful change, such as a wider date range.

## Ticket

A Ticket shows the date, Artist, the reason for the pick, venue, day and time, price if the source has one, and a link to the source listing: Ticketmaster, or the JamBase event page. When the source has a real photo, the Ticket shows it beside the details on desktop and above them on phones. A missing or generic source photo stays out. While a Concert is not yet on general sale, a Ticket names its next presale that has not ended and when it starts. VIP packages do not count.

Dates and times read on the venue's clock. A visitor in the same time zone sees "7:30 PM". A visitor anywhere else sees the venue's zone too, as in "7:30 PM CST". Presales open at one moment, so they stay in the visitor's zone.

The reason comes from the ranker. Every other fact comes from the source record, per [ADR 0002](../adr/0002-facts-never-pass-through-the-llm.md). A missing time or price is left out. The app never invents a value, which fixes the old fake "8:00 PM".

The visitor saves from the Ticket. Saving leaves it open and confirms where it was kept. The dialog closes with its close button, Escape or the backdrop and returns focus to the Concert that opened it. Skip, dragging and the one-by-one deck were removed by the owner's decision on November 7, 2026. Every action works from the keyboard.

A Ticket and each Saved Concert offer "Add to calendar", which downloads one `.ics` file built in the browser with no request. It carries the Lineup, venue, source link and start time on the venue's clock (`TZID`), all from the source record. A Concert with no start time becomes an all-day event on its date, and none gets an end time, because the source reports none.

## Shared Posters

A Poster or a single Ticket can be shared by link. The Share button uses the browser's share sheet where there is one and copies the link otherwise. A link names a Shared Poster, which anyone can open on any device without a Search, a model call or a sign-in, and a Ticket link opens that Poster with the Ticket open.

The browser never sends a Poster. When a Search finishes with picks, the server keeps what it produced under a Search ID it hands to that browser, and sharing promotes it. A Shared Poster holds the Recommendations and the Search's reading and lasts 90 days. It never holds the person's coordinates. Artists from their Taste can appear in its reading and reasons, as they do on screen. Past Concerts drop out whenever it is read, so an old link shows only what is still to come. A cached example Poster has no Search ID, so it has no Share button.

The `/p/[id]` page says "Shared Poster", shows the date it was made and the reading as chips, and has a Search box that fills the home Search without running it. A link preview shows a generated Poster image.

## Saved Concerts

A guest's Saved Concerts live in `localStorage` and stay on one device. A Saved Concert stores its source ID and the facts needed to show it, and a page lists them with past Concerts removed.

An optional account keeps Saved Concerts on every device. Sign in from the menu with Google, or with an email and password after confirming the email. While signed in, a Save goes to the account, and the API reads the Concert's facts from its source before storing it: Ticketmaster, or the JamBase Catalog. Signing in moves the device's guest saves into the account. Each one leaves the device only once the account holds it, and any the API cannot confirm with their source stay on the device for the next sign-in. Signing out shows none of the account's saves. The Account page offers sign-out and account deletion, which needs a sign-in from the last 10 minutes.

## Spotify shelf

An allowlisted visitor who connects Spotify sees a separate dark shelf beneath the Poster, listing Concerts by their own Artists. Before a Search, the shelf shows those Artists near a shared location for the next two months. Spec in [03-taste](03-taste.md).

## Errors

Each failure names what happened and what to do. An upstream outage says which service failed, and a rate limit says when to try again. A dropped stream offers a retry.
