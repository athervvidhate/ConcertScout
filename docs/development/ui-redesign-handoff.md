# UI redesign handoff: bring the Fluid Search study into the app

Written November 7, 2026, for the agent that builds the new interface. The owner approved the design direction and the palette, then handed the build to you. Read this whole file before you start.

## The job

Rebuild the production frontend (`frontend/`, Next.js 16, React 19) to match the approved study in `docs/mocks/fluid-search/`, wired to the real API that is already deployed. The study is a standalone page that replays captured Searches; the app must do the same things with live Server-Sent Events, real Saves, Spotify, Taste and the rest of the product that the study leaves out.

Production today: frontend `https://concertscout.app`, API `https://api.concertscout.app`, both on Vercel, deployed from `development` at `967d4d8` with Search on. Do not deploy, change DNS, Vercel settings or environment variables without the owner's explicit go-ahead.

## Read first

1. `AGENTS.md`, `GLOSSARY.md` (use its terms: Search, Concert, Artist, Poster, Ticket, Taste, Saved Concerts), `docs/specs/00-overview.md`, `docs/adr/` (facts come from the source record, never the LLM; Spotify data never reaches an LLM).
2. `docs/mocks/fluid-search/README.md`: every design decision, the layouts by result count, what moves and how. Then open `docs/mocks/fluid-search/index.html` in a browser and run each study Search from the bar at the bottom (8, 4, 3, 2, 1, 0 results). `journey.mp4` is a 42-second walkthrough of an older round; the page is the source of truth.
3. `docs/specs/04-interface.md`: the current interface spec. **The study replaces much of it** (see "Spec changes" below).
4. `docs/development/testing.md` (contract vs browser test boundaries), `docs/development/local.md`, `docs/development/hosting.md`.
5. `frontend/lib/use-search.ts` and `frontend/lib/search.ts`: how the app consumes the SSE stream today.

## Decisions already made by the owner

- **Palette: Moss, light and dark.** Tokens are in `docs/mocks/fluid-search/style.css` (`:root` and `:root[data-mode=dark]`). No cream, no orange field, no rotating sun. Dark mode follows the system setting; offer a manual switch in the header menu. Both modes meet 4.5:1 for text and buttons.
- **Type:** Anton for display (Poster names, counts, headline), Bricolage Grotesque for UI and body. Fonts are in `docs/mocks/fluid-search/fonts/`; load them with `next/font/local`.
- **Surface:** flat paper, solid surfaces, hairline borders, one small shadow. No gradients as decoration, no blurred blobs, grain or frosted glass. Colour comes from the Concert photos.
- **Results:** Grid and List only, switched by two icon buttons with accessible names. No one-by-one deck. Layout follows the count (0 empty state with three ways forward; 1 a solo Ticket; 2 halves; 3 one large and two stacked; 4 halves; 5 to 8 large, stacked, then thirds and halves). For 3 or fewer, "Also playing, not picked" lists the other candidate Artists.
- **Home:** search box and pitch, a labelled photo strip of what example Searches found, How a Search works (a real Search replayed in three panels), Make it yours, footer. The strip shows cached top picks of the example Searches, refreshed by the nightly warm job, so a visit or a click on an example **never triggers a paid Search**. A visitor with Spotify connected sees their own Artists playing near them instead. No place is ever inferred from an IP address.
- **Motion:** the picked Artist's name travels as one pill into the card title; the Ticket opens from the card photo and returns to the card's exact frame; switching views fades out and raises the new view card by card; the How panels hold the height of their finished state. Reduced motion shows end states immediately. The README's "What moves" section lists every motion.

## What the study does not cover, and must survive

The study is a front-end shell. Everything below is in production and must keep working in the new design (find each in `frontend/components/` and its spec):

- Spotify connect and the home shelf (`spotify-shelf.tsx`, spec 03), Your Taste panel and imports (`taste-panel.tsx`), Saved Concerts page (`app/saved`), privacy page and credits.
- Artist panel and the first-Ticket Artist hint, Search reports ("Tell us", Resend), the Elsewhere board for empty Posters, the location button in the search box, presales and general sale on Tickets, dates grouped by venue, show-title trimming (`lib/show-title.ts`).
- Turnstile bot check and the visitor limit, error and retry states, the 503 when Search is off.
- Ticket decisions: production has Save and Skip with drag (Motion). The study has Save only, and opens a Ticket as a dialog. **Ask the owner** whether Skip and drag stay before removing them.

## Wiring the study to the API

The study replays the same SSE events the API sends from `POST /search` (`api/concert_scout/app.py`): `status`, `interpreted`, `candidates`, `pool`, `poster`, `elsewhere`, `error`, `done`. The study's `data.js` holds real captured payloads, so its field names show what each view needs. Check every field the study reads against the current API models before building on it; where the study shows something the API does not send, leave it out (never invent a value) or add it to the API with a contract test.

Backend work the design needs:

1. **Home strip from cached example Searches.** The nightly `/warm` cron (CRON_SECRET, 23:00 UTC) already warms pools for 12 cities. The strip needs the finished Posters of the home example Searches served from cache without a model or Ticketmaster call on page load. Design the smallest endpoint or cache read that does this, with a contract test proving a strip request makes no paid call.
2. **Empty state actions** ("Look at the next three months", "Look anywhere", "Change the Search"): check which ones the API already supports (the Elsewhere event covers "anywhere" for one Artist or tag) before adding anything.
3. **"Also playing, not picked"** uses `candidates`; confirm it carries the names the view needs.

## Work in flight elsewhere: coordinate, do not overwrite

- **Accounts** (branch `accounts`, being built in the root checkout at `/Users/atherv/Projects/concert-scout`): Supabase auth, synced Saved Concerts, changes to `site-header.tsx`, `poster.tsx`, `lib/saved.ts`, `lib/account.ts`. The new header and Save must sit on top of that work once it lands. Plan in `docs/research/2026-11-07-account-experience-design.md` (on that checkout).
- **Coverage** (branch `jambase-national`, worktree `coverage-audit`): more Concert sources. May add fields to Concerts.

Start from `development` after these land if the owner says they are close; otherwise keep your header and Save changes small and rebase.

## Spec changes

Update the specs in the same PRs as the code (the repo rule is that specs match the app):

- `docs/specs/04-interface.md`: replace the tokens, type, sun, "Fine print" loader and Ticket colours with the study's Moss tokens, two fonts, working view and Ticket dialog. Keep the sections that still hold (Artist panel, hint, reports, Elsewhere, interaction rules, 44px targets, 390 and 1280 checks).
- `AGENTS.md` names `docs/mocks/fine-print-loader.html` as the approved mock. Point it at `docs/mocks/fluid-search/` and delete the old mock (no compatibility layers).
- `docs/specs/04-interface.md` asks for Web Animations API and Motion; the study uses GSAP 3.13 (Flip, ScrollTrigger). Pick one: Motion is already a dependency and should cover everything here; add GSAP only if Motion cannot do a specific effect, and say why.

## Suggested order (each a PR against `development`, each leaving the app working)

1. Moss tokens, fonts, light and dark mode, header and menu. No layout change yet.
2. Home: search box, examples, photo strip (with the cached-strip backend and its contract test), How a Search works, Make it yours, footer.
3. Working view on real SSE: status steps, interpreted chips, candidate names narrowing to the picks.
4. Results: layouts by count, Grid and List, name-into-title motion, "Also playing, not picked", empty state.
5. Ticket dialog with Save, Artist panel, presales, other dates; decide Skip and drag with the owner.
6. Fold in Spotify shelf, Taste, Saved Concerts, Elsewhere, reports, privacy in the new style. Delete the old components and the old mock.

Each PR: contract tests for any API change, browser tests per `docs/development/testing.md` at 390 and 1280 with and without reduced motion, lint, types, and the app left running locally. While iterating, run targeted browser tests; run the full end-to-end suite before each PR.

## Not verified in the study

Real-device frame rate, screen-reader review, real Spotify accounts, and live (not replayed) Search timing. Check these in the real app before calling the redesign done.

## Rules that bite

- Atherv Vidhate is the only author: no AI attribution in commits, PRs or comments.
- Branch from `development`, PRs against `development`. Do not merge or deploy without the owner.
- Never put a personal email in a request header.
- The design skills under `.claude/skills/` (frontend-design, design-taste-frontend, impeccable) are installed locally and gitignored; use them if present, never commit them.
