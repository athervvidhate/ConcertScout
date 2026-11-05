# Tickets

The build grows in vertical slices. After each ticket, a person can run the app and see more working, so the product never sits half-rebuilt. Each ticket becomes a GitHub Issue that an agent can pick up alone.

| # | Ticket | Needs | User-visible result |
|---|---|---|---|
| 1 | Walking skeleton | None | Type a city, see real Concerts stream in |
| 2 | Interpreter | 1 | Plain-text Searches work |
| 3 | Concert pool and cache | 1 | Date-less and big-city Searches work and repeat fast |
| 4 | Artist matching | 2, 3 | Concerts are ordered by Taste |
| 5 | Ranker and Assemble | 4 | Up to 8 picks, each with a reason |
| 6 | Eval harness and judging tool | 5 | Hand-judged Searches can score the pipeline |
| 7 | Poster and Fine print loader | 5 | The new design replaces the plain list |
| 8 | Tickets and Saved Concerts | 7 | Save and Skip work and persist |
| 9 | Home with nearby Concerts | 3, 7 | Useful page before any Search |
| 10 | Limits and abuse protection | 5 | Safe to expose publicly |
| 11 | Last.fm and ListenBrainz Taste | 5 | Import a Taste by username |
| 12 | History file and pasted lists | 5 | Import a Taste from a file or paste |
| 13 | Spotify OAuth and shelf | 7 | Allowlisted users see their shelf |
| 14 | Tracing and cost tracking | 5 | Each Search has a trace and a cost |
| 15 | Hosting | 10, 14 | The app runs at a public URL |
| 16 | Portfolio finish | 7, 15 | README, privacy page and attribution |

Ticket numbers map to GitHub Issues #17 to #32, so ticket 1 is #17 and ticket 16 is #32.

Tickets 6, 9, 10, 11, 12, 13 and 14 can run in parallel once their needs are met.

Ticket 1 removes the old ADK app, frontend and deploy scripts, so no ticket works around them.

Every ticket must add tests, pass CI, and keep the app running locally.
