# 03 - UI and frontend research

Researched 2026-11-04. Scope: `frontend/` (Next 15.2.4, React 18 runtime with @types/react 19, Tailwind 3, v0 output). Items marked UNVERIFIED rest on secondary sources, memory, or a page I could not fully read.

## Bottom line

1. **Patch now, before any redesign.** Next 15.2.4 is missing every 2025-12 to 2026-11 fix, including the CVSS 10 React Server Components RCE (React2Shell). Go straight to **Next 16.4.5** (Active LTS, 2026-11-03). The minimum same-line stopgap is 15.5.29, but 15.5 is only "Maintenance LTS". Take React 19.3 with it (Next 16.4 ships it).
2. **Stay on Next.js; skip TanStack Start.** The app is small and its backend is separate FastAPI. Start 1.0 is stable but needs Vite 8, and I could not confirm RSC support. Next gives OG images, streaming, `<ViewTransition>` integration and Vercel hosting already in use.
3. **Rebuild the visual layer, don't restyle it.** Delete about 45 unused shadcn components. Move to Tailwind 4 and shadcn's current CLI (Base UI default since 2026-07-03; Radix still supported). Keep only what is used (button, dialog, select, tooltip) plus new Questionnaire-style components.
4. **Pick one of the three art directions below and commit.** Recommended: **A "Wheatpaste"** (gig-poster typography, duotone-normalised images). It is the cheapest way to hide inconsistent Ticketmaster images and is the least like the SaaS look.
5. **Replace the fake timer with real streamed steps.** The backend already returns an `events` array with `function_name` and `function_args` (`lib/api.ts`). Stream those over SSE and render a step list, then stream result cards as they resolve. Make clarifying questions a structured form, not a bot bubble. Show a one-line "why this" per result. Let the user edit the parsed search as chips and re-run.
6. **Hybrid search UI:** one free-text box that resolves into editable filter chips (city, dates, genres, artists, price cap). Add shareable URLs (`/results?q=...&city=...`), `.ics` export, outbound ticket links, a MapLibre map, and a per-result OG image.
7. **Quality bar:** WCAG 2.2 AA, CWV at p75 (LCP <= 2.5 s, INP <= 200 ms, CLS <= 0.1), Playwright e2e plus `toHaveScreenshot` for 3 to 4 key states. Skip Storybook.

## 1. Stack status (late 2026)

**Next.js.** Latest is 16.4 (2026-10-06): React 19.3, Cache Components recommended and default in new apps, becomes default in Next 17 ([nextjs.org/blog/next-16-4](https://nextjs.org/blog/next-16-4)). Blog index: [nextjs.org/blog](https://nextjs.org/blog). Next now runs a formal monthly security-release process ([2026-07-13](https://nextjs.org/blog/next-security-release-program)); next one expected early December (UNVERIFIED, inferred from cadence).

**Security timeline relevant to 15.2.x** (all primary, nextjs.org):
- 2025-12-03, CVE-2025-66478 / React2Shell, CVSS 10.0, unauthenticated RCE in the RSC protocol; hits all 15.x and 16.x App Router apps; 15.2 line fixed in 15.2.6; secrets should be rotated if exposed ([advisory](https://nextjs.org/blog/CVE-2025-66478)). 15.2.4 is vulnerable. React 18 in package.json does not protect you: the App Router runs Next's bundled React.
- 2026-09-22, critical RCE in Node `ImageResponse` (`next/og`), GHSA-vcvr-r3jv-pc5j; affects `>=16.2.0 <16.3.6`; 15.x not affected (hardening only in 15.5.26) ([post](https://nextjs.org/blog/nextjs-security-update-september-22-2026)).
- 2026-09-30, scheduled release: 1 high (SSRF in Image Optimization when `remotePatterns` set, CVE-2026-94483), 5 medium, 1 low; fixed in 16.3.8 / 15.5.27. A critical and a high were postponed ([post](https://nextjs.org/blog/september-2026-security-release)). This app almost certainly uses `remotePatterns` for Ticketmaster images, so the SSRF applies.
- 2026-10-14, out-of-band: two critical + one high; fixed in 16.4.1 / 15.5.28 ([post](https://nextjs.org/blog/nextjs-security-update-october-14-2026)). (a) `use cache` typed-array RCE (16.x with Cache Components only). (b) Unauthenticated RCE in Image Optimization API via SVG/`sharp` on glibc Linux, CVE-2026-96889; workaround `sharp >= 0.35.5`. A third-party source puts the affected range at 10.0.0 to 15.5.27 (UNVERIFIED; the primary post gives no range), so assume 15.2.4 is affected. (c) Server Actions DoS (high), App Router with at least one Server Action.
- 2026-11-03, latest: 16.4.5 / 15.5.29; one high, five medium, mostly Cache Components and self-hosted issues ([post](https://nextjs.org/blog/november-2026-security-release)).
- So the "critical Sep and Oct" lead is confirmed: Sep 22 (16.x only) and Oct 14 (two criticals, one reaching 15.x via image optimization).

**Upgrade path:** 15.2.4 to 16.4.5 crosses two majors of changes (Next 16: Turbopack default, async request APIs, `middleware` to `proxy`, `next lint` removed). Next supplies `npx next@canary upgrade --agent=latest` for agent-assisted upgrade (16.4 post). Do it before redesign work; the app is small (805 lines in `app/` + `components/`). Cache Components is optional for this app (dynamic, no personalised cache); do not enable `use cache` unless needed, which also sidesteps the 2026 cache advisories. UNVERIFIED: exact Next 16 breaking-change list; check the upgrade guide.

**React 19.3** (2026-09-09): `<ViewTransition>` and Fragment refs now stable ([react.dev](https://react.dev/blog/2026/09/09/react-19-3)). Useful for the progress-to-results and card-to-detail transitions.

**Tailwind:** v4.3 (blog 2026-05-08), 4.3.1 listed 2026-06-12 via a tracker; official blog index not read, so treat the exact patch as UNVERIFIED ([search result](https://rss-parrot.net/web/feeds/tailwindcss.com.blog)). v4 is CSS-first config; the current v3 setup plus `tailwindcss-animate` should migrate (shadcn moved in Feb 2025).

**shadcn/ui:** Base UI became the default component base on 2026-07-03; Radix remains supported, React Aria added as a third base ([changelog mirror/secondary](https://www.shadcnblocks.com/changelog/new-feature-base-ui-support); official: [ui.shadcn.com/docs/changelog](https://ui.shadcn.com/docs/changelog)). Base UI hit 1.0 in 2025-12 (secondary, UNVERIFIED version numbers). Official changelog also lists Questionnaire (clarification flows, Aug 2026), Human in the Loop helpers (Aug), `cn` package (Sep), and AI Elements built on shadcn (Oct). Recommendation: new init picks Base UI; with only four primitives in use, either works. Prefer the default for maintenance.

**AI Elements deprecation: confirmed, with nuance.** The vercel/ai-elements README and elements.ai-sdk.dev say the project "is moving to shadcn/ui" and "will be deprecated at the end of November 2026" ([repo](https://github.com/vercel/ai-elements), [site](https://elements.ai-sdk.dev/)). shadcn's October post says it replaces "AI SDK Elements"; patterns are copy-in compositions, no package, 21 patterns including Chain of Thought, Plan, Queue, Task, Tool, Sources, Inline Citation, Suggestion, Confirmation ([shadcn changelog](https://ui.shadcn.com/docs/changelog/2026-10-ai-elements); page not fully read). Implication: if you borrow, use the shadcn version. Don't take the chat-bubble look; borrow Task/Queue/Sources structure only.

**TanStack Start:** 1.0 stable reported 2026-10-13, requires Vite 8, `.inputValidator()` renamed (secondary sources; the 2025-09-23 RC post is primary: [tanstack.com](https://tanstack.com/blog/announcing-tanstack-start-v1)). A reflected-XSS CVE-2026-102989 in 1.168.x fixed in 1.169.39 (secondary, UNVERIFIED). RSC support not confirmed. Verdict: credible alternative, not worth a framework swap for a UI overhaul. Revisit only if you drop Vercel.

## 2. What reads as AI-generated in 2026

Sources are mostly blogs, no survey data: [superdesign.dev](https://superdesign.dev/blog/why-ai-design-looks-generic), [925studios](https://www.925studios.co/blog/ai-slop-design-tells), [avoid-ai-design (GitHub)](https://github.com/funboy322/avoid-ai-design), plus the frontend-design guidance. The common thread: output converges on the training-data average, which looks like shadcn plus a purple gradient. Tells, with this app's instances:

| Tell | In this app |
|---|---|
| Purple-pink-blue gradients, glow shadows (`shadow-purple-500/10`) | everywhere |
| Sparkles icon for "AI" | header/prompt |
| Robot avatar chat bubbles for a search task | `ai-chat-bubble.tsx` |
| Identical rounded card grid, same border/radius, scale-on-hover | `concert-card.tsx` (`hover:scale-[1.02]`) |
| Per-row hover tint with a different accent per icon (purple/blue/pink) | card meta rows |
| Icon + label on every field (calendar, pin, note) | card meta rows |
| Permanent dark mode, grey 1px borders, Inter/system font | globals/layout |
| Fake progress ("Analyzing... Searching... Almost done" by elapsed seconds) | `search-prompt.tsx` |
| Gradient wash over images, "•"-joined meta | card |
| Newer second-wave tells to avoid when escaping: cream + terracotta, near-black + one acid accent, hairline broadsheet, mono ALL-CAPS eyebrow labels, "→" on every link | n/a |

What distinctive teams do instead: a committed point of view in one place (type, or a colour field, or imagery) with everything else quiet; real content as the hero (an actual event, not a tagline); hierarchy through size and weight differences, not boxes; motion only in response to user action or to mark one orchestrated moment; copy that is specific ("3 shows near Brooklyn this weekend") not branded ("Discover your next vibe"). Evaluate on rendered screenshots, not code.

## 3. Live-music references and three art directions

Primary pages for DICE and RA returned 403 to my fetcher, so descriptions are from press: [It's Nice That on DICE's 2022 rebrand](https://www.itsnicethat.com/news/patrick-duffy-dice-rebrand-graphic-design-040422) (hand-made, "fanmade", stick-and-poke logo, colour fields evoking a show), [Design Week](https://www.designweek.co.uk/issues/4-10-april-2022/dice-rebrand/) (tagline "Find the fan in everyone", mobile-first), [RA redesign history](https://en.wikipedia.org/wiki/Resident_Advisor) (2014, 2021 React rebuild). Everything beyond that is UNVERIFIED, from memory:
- **DICE:** mobile-first, full-bleed event art, strong colour per event, price shown up front, waiting-list and no-resale ethos. Takeaway: let the event's own art carry the screen; price on the card.
- **Resident Advisor:** dense, text-first listing by date, sharp small type, venue and lineup more prominent than imagery. Takeaway: scannable date-grouped rows beat card grids for browsing.
- **Bandsintown / Songkick:** artist-tracking and notification-led; the web UI is a utility. Takeaway: "track this artist" is the retention loop, not the browse page.
- **Spotify Live Events, Shazam:** discovery tied to listening identity; Shazam's single-action simplicity. Takeaway: personalisation signal (artists you follow) should visibly explain results. UNVERIFIED.
- **Gig posters, festival identity, editorial press (e.g. Pitchfork/Quietus):** huge condensed or slab type, 1 to 2 ink colours, rough registration, bill-style lineup lists. This is the ownable vernacular: generic SaaS tools cannot fake it cheaply.

**Ownable idea:** treat each result as a poster/bill line rather than a product card, and make the AI's reasoning the "liner note" under it.

Font licences below are from memory; check each foundry page before shipping (UNVERIFIED).

**A. Wheatpaste (recommended).** Poster-bill list on cool paper with riso inks.
- Type: Archivo (variable, width axis, SIL OFL, Google Fonts) at condensed/expanded widths for headlines, Archivo normal width for body. One family, widths do the work.
- Colour: paper `#ECEEF0`, ink `#101114`, riso blue `#1F3BFF`, signal yellow `#FFD60A`; yellow only for the "pick" marker.
- Layout: date-grouped rows like a street bill; giant condensed date numerals left, artist in expanded caps-free heavy weight, venue/price right-aligned; left-aligned throughout; image as a small square duotone (blue ink on paper) via CSS `mix-blend-mode: multiply` + SVG filter.
- Motion: one orchestrated moment, results "paste up" in sequence when the stream resolves; no hover scaling; rows expand on click.
- Imagery: all images normalised to the same duotone and crop (see below).

**B. Liner Notes.** Magazine-feature layout, serif voice.
- Type: Newsreader (OFL, display optical size) for headlines and picks' rationale, Hanken Grotesk (OFL) for UI and data.
- Colour: pale sage paper `#E8EDE6` (avoid the cream default), ink `#0F1A14`, bottle green `#0F3D2E`, ochre `#E0A100`.
- Layout: top pick is a lead feature with large image and a pull-quote "why"; the rest in a two-column ranked column with justified-left text, ~65ch; works well since explanations are the product.
- Motion: view-transition from list item to detail; nothing ambient.
- Imagery: one hero image only; others as small crops or none.

**C. Sodium Night.** Venue-first map, dark by purpose (night out).
- Type: Cabinet Grotesk (Fontshare, free commercial use under ITF Free Font License) for headings, Satoshi (Fontshare) for text.
- Colour: night ink-blue `#0B1220`, sodium amber `#FFB000`, fog `#C9D3E0`, brick `#B4412C`. No purple, no glow.
- Layout: split map and list (MapLibre dark style); time scrubber along the bottom for dates; mobile = map with bottom sheet.
- Motion: map fly-to on selection; sheet snaps.
- Imagery: small square thumbnails; map is the hero.

**Inconsistent Ticketmaster images.** Discovery API returns multiple images per event with `ratio` (16_9, 3_2, 4_3), `width`, `height`, `fallback` flag and `attribution` ([docs](https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/); page only read to char 100000). Pick the largest 16_9 or 3_2 image whose `fallback` is false; render in a fixed aspect-ratio box with `object-fit: cover` and a focal bias toward the top third; apply a uniform treatment (duotone in A, grayscale-to-hover in B, small thumbnail in C); if `fallback: true` or missing, show a typographic placeholder (artist name set large on a flat colour) rather than the stock image. Never gradient-overlay text on the image; keep text outside. Serve through `next/image` with sizes, `priority` only on the first image. Check Ticketmaster terms for required attribution/linking before launch (not read; UNVERIFIED).

## 4. UX for agentic work

- **Real progress.** Perplexity's docs show streaming text and sources progressively, with each search producing its own results event and numbered source ids mapped to citations ([docs](https://docs.perplexity.ai/docs/cookbook/articles/streaming-citations)). Pattern to copy: phase indicator, then sources appear, then answer. Vercel AI SDK supports typed, id-updatable data parts and transient parts for exactly this ([ai-sdk.dev](https://ai-sdk.dev/docs/ai-sdk-ui/streaming-data)); shadcn AI Elements has Task, Queue, Tool, Plan components as references. For this app: stream backend events (`parse query`, `search Ticketmaster: city, dates`, `N events found`, `rank`) as steps with status (pending/running/done/failed) and real counts. Replace the 30/60/120 s text switch. Keep the 3-minute window honest by showing the current step name and elapsed time, not a percentage.
- **Skeleton to result.** Show the parsed query as chips immediately; show skeleton rows only as placeholders for the number of events found so far; insert cards as each is ranked; keep layout stable (CLS). Allow reading partial results while the run continues, with a "still checking N more" line.
- **Clarifying questions as UI.** Replace the follow-up bot bubble (and the string concatenation of `conversationMessages`) with a structured prompt: a short question plus option chips or a date/city field, answered inline with a Skip. shadcn's Questionnaire component targets exactly this ([changelog](https://ui.shadcn.com/docs/changelog)). Backend should return a typed `clarification` object `{field, question, options}`; this is a backend contract change.
- **Explain recommendations.** One sentence per result stating the matched criteria ("Indie, Fri 14 Nov, 2.1 mi from Williamsburg, under $40") with the matched chips highlighted; link to sources. Perplexity-style citations pattern; ChatGPT search and Linear's agent UX not fetched, UNVERIFIED beyond that.
- **Edit after running.** Keep the query as editable chips on the results page; changing a chip re-runs only that stage and updates the URL. Offer "Refine" over starting new chat. Provide cancel during the run.
- **Feedback.** Per-result "not for me" (hide + reason) and a single thumbs on the whole set; feed this into a tracked-artists list later. Keep it unobtrusive; no star ratings.
- **Free-form vs structured vs hybrid.** Free-form alone is slow (3 min!) and unrepeatable; filters alone lose the "find something like X near me this weekend" value. Hybrid wins: free text parsed into visible, editable structured filters; direct filter edits skip the LLM and hit the API directly, which also cuts latency and cost. Suggestions row for first-time use.

## 5. Concert-specific features

- **Map:** MapLibre GL JS (BSD, open source; v6 line, ESM only per [docs](https://maplibre.org/maplibre-gl-js/docs/)) with free-tier tiles (MapTiler/Stadia/Protomaps, check terms). Mapbox GL is proprietary with usage-priced tokens; no need here. CSP needs `worker-src 'self'` and `img-src data: blob:`. Lazy-load the map chunk.
- **Calendar export:** generate `.ics` (RFC 5545) client-side via a small maintained library (e.g. `ics` package; check maintenance) plus "Add to Google Calendar" URL. Include venue address and ticket URL; times in the venue's timezone.
- **Tracking artists:** needs accounts or at minimum local storage; defer. Start with "save" in localStorage, email/push later.
- **Shareable results:** `/results?q=...` is already a route; make it server-renderable from params, plus `opengraph-image` using `next/og` showing top 3 shows. Note the 2026 `next/og` Node RCE and image advisories: stay on 16.4.5 and prefer Edge `ImageResponse` (not affected by Sep 22 issue).
- **Mobile-first:** design at 390 px first; sticky bottom action (ticket link); 44 px targets.
- **PWA:** manifest + installable only; skip offline/service worker until there is a reason. Saved shows offline is the one real use case (venue with bad signal).
- **Ticket deep links:** use event `url` (and `outlets`, `sales.presales.url`) from the Discovery API; open in new tab with `rel="noopener"`; label "Tickets on Ticketmaster" (name the destination). Affiliate fields not documented on the page read; UNVERIFIED.
- **Price display:** API `priceRanges` has `min`, `max`, `currency`, `type: standard` only ([docs](https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/)). Show "from $X" only when present, else "Price at checkout"; add "before fees" if unsure (fee inclusion not documented; UNVERIFIED). Rate limits 5/s and 5000/day matter for the backend, not the UI.

## 6. Quality bar

- **WCAG 2.2** adds 2.4.11 Focus Not Obscured (AA), 2.5.7 Dragging Movements (AA), 2.5.8 Target Size minimum 24 px (AA), 3.2.6 Consistent Help (A), 3.3.7 Redundant Entry (A), 3.3.8 Accessible Authentication (AA); 4.1.1 removed ([W3C](https://www.w3.org/TR/WCAG22/)). Practical: map needs a list alternative (no drag-only), sticky bars must not cover focus, progress updates in an `aria-live="polite"` region, clarification form labelled, colour contrast checked on A/B/C palettes, `prefers-reduced-motion` honoured.
- **Core Web Vitals:** LCP <= 2.5 s, INP <= 200 ms, CLS <= 0.1 at the 75th percentile, mobile and desktop separately ([web.dev](https://web.dev/articles/vitals)). Risks here: remote Ticketmaster images (set `sizes`, `priority` for LCP only), font loading (`next/font`, one family), map bundle (lazy), streaming insertion causing CLS (reserve row height).
- **Motion:** use React 19.3 `<ViewTransition>` for list-to-detail and stream reveals; add the `motion` library only if gestures (bottom sheet) need it. UNVERIFIED that Safari support is adequate for all cases (React notes a Mobile Safari crash fix in 19.3).
- **Testing:** Playwright for the flows (search, stream, clarify, edit chips, open ticket link) with the backend mocked via SSE fixtures; `toHaveScreenshot` for 3 to 4 states (empty, running, results, clarification) at mobile and desktop, plus `@axe-core/playwright` for a11y (both from memory, UNVERIFIED versions). Run in the same container image in CI to avoid font/OS drift.
- **Storybook:** skip. Around 6 components, one app; Playwright states cover it. Add only if a second consumer appears.
- **Cleanup:** remove unused shadcn components and Radix packages; drop `next-themes` if single theme; rename package from `my-v0-project`; fix `react` pin to 19.x to match @types.

## Open items for the owner
1. Choose art direction (A, B, or C).
2. Confirm backend can stream events (SSE) and return typed clarifications; this gates section 4.
3. Confirm Ticketmaster terms on image use, attribution, and affiliate links.
