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

A Poster shows up to 8 Recommendations, ranked and set in festival-style tiers: one headliner, two second-tier names, and the rest beneath. If fewer than 8 Concerts qualify, the Poster is shorter. It never pads with weak picks.

Each Artist appears once. Their other dates sit behind "more dates" on the Ticket. Clicking a name opens its Ticket. Saved names are underlined with a "saved" label. Skipped names are struck through at 35% opacity and stay on the Poster.

If nothing qualifies, the page says so and offers the nearest useful change, such as a wider date range.

## Ticket

A Ticket shows the date, Artist, the reason for the pick, venue, day and time, price if the source has one, and a link to buy from Ticketmaster. When the source has a real photo of the lead Artist or the Concert, a band across the top shows it, with a light tint of the Ticket's color. A Ticket with only Ticketmaster's generic placeholder has no band. While a Concert is not yet on general sale, a Ticket names its next presale that has not ended and when it starts. VIP packages do not count.

The reason comes from the ranker. Every other fact comes from the source record, per [ADR 0002](../adr/0002-facts-never-pass-through-the-llm.md). A missing time or price is left out. The app never invents a value, which fixes the old fake "8:00 PM".

The visitor can Save or Skip with buttons, or by dragging the Ticket right or left. After either action, the next undecided Ticket opens. After the last one, an end panel lists what was saved from this Poster and links to the Saved page, or says nothing was saved. Every action is a button, so all of them work from the keyboard.

## Saved Concerts

Saved Concerts live in `localStorage`, so they need no account and stay on one device. A Saved Concert stores its source ID and the facts needed to show it, and a page lists them with past Concerts removed. Accounts may come later, and they are not part of this rebuild.

## Spotify shelf

An allowlisted visitor who connects Spotify sees a separate dark shelf beneath the Poster, listing Concerts by their own Artists. Before a Search, the shelf shows those Artists near a shared location for the next two months. Spec in [03-taste](03-taste.md).

## Errors

Each failure names what happened and what to do. An upstream outage says which service failed, and a rate limit says when to try again. A dropped stream offers a retry.
