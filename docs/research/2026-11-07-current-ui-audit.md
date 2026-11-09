# Concert Scout: critical UI audit and next design direction

Date: November 6–7, 2026. Design study; no production UI or deployment changes.

## Verdict

The current interface has a recognizable identity, but too many parts compete to express it at the same time. Anton and Bricolage are worth keeping. The full-screen rotating sun is the first thing I would remove from working screens. The combination of radial stripes, saturated orange, oversized Artist names, pastel Ticket, dotted divider, dot-matrix dates, and large decision buttons makes even a two-Recommendation Search visually loud.

This is a design judgment, not the result of a user study. The measurable problem beneath it is hierarchy: useful facts and actions sit below decorative or repeated information. A calmer app can remain unmistakably Concert Scout.

## What was actually inspected

The deployment checkout was changing during this task. To avoid reviewing a moving target, I exported committed `f1defa4f65b284077283597e8848769dbc46ee05` from the product worktree into `/tmp/concert-scout-ui-audit`. This is the home/listings polish version, ahead of root development `6ceba19`. Another research task inspected a later hosting branch; its version is recorded separately. This is not a claim about the eventual production deployment.

- Own Next.js frontend: `http://127.0.0.1:3217`.
- Own API: port 8217, using the repository's browser-test composition, real pipeline and isolated temporary Redis, substituted domain adapters and model. CORS and fixture callback ports changed only in the temporary snapshot.
- No live Searches, purchases, account connection or provider costs. “Contract Artist”, its dates, venues and Spotify-logo image are **test fixtures**. The logo is not evidence that real Tickets use a Spotify logo as a photo.
- Visually inspected Home, Poster/Ticket, Artist panel with missing details, Saved Concerts, Your Taste, and empty Search through the shared browser. Save advanced the Ticket; the saved Concert appeared on Saved Concerts. Escape dismissed the Artist/Taste panels.
- Automated evidence capture additionally exercises loading, interrupted stream, retry, privacy and reduced motion at 1280 and 390 CSS pixels. The capture files were not kept. All 18 captured states fit the viewport width. Save began at y=937 on a 1280×844 viewport and y=864 on a 390×844 viewport; both were below the initial fold. Reduced-motion retry succeeded and the background animation computed to `none` at both sizes.
- Actual Spotify consent, connected shelf, location permission, real device gestures, eight-Recommendation live Poster, slow physical-device performance and screen-reader speech were not audited. Existing tests are not a substitute for these checks.

## Findings and recommendations

| Priority | Finding | Evidence and implication | Proposed change |
|---|---|---|---|
| High | Background motion never gives the eye a resting place | Observed across Home, Poster and Saved. Source sets a repeating conic gradient rotating every 90 seconds on a fixed 230vmax element. Even slow motion affects the entire reading field. No GPU cost claim was measured. | Keep a small static sun as a signature. Remove the moving field from Search, Tickets, Saved and panels. Compare a solid orange Home with a quiet pale-green Home before choosing. |
| High | Poster and Ticket compete vertically | In the shared browser at 1402×877, two fixture Recommendations put Save/Skip at y=944 before the Artist hint was dismissed. The first Ticket began at y=444. A larger Poster risks more scrolling; that eight-pick case remains unmeasured. | Desktop: compact Poster selector alongside the Ticket. Mobile: compact accessible selector above it. Keep facts and actions together; do not sacrifice legibility to force arbitrary content into one viewport. |
| High | The Ticket reserves space for a metaphor instead of the task | At 390px the purchase strip is 76px wide, while the content area is 290px. “Admit one” is decoration: the Ticket is not proof of purchase. A missing-price Ticket leaves that strip particularly sparse. | Remove “Admit one”. Put date, venue and price in a readable facts block; put the source link and Save together. A clipped or perforated edge can remain decorative without clipping focus rings or hit targets. |
| High | Interpretation is visible but difficult to correct | Observed place summary; source reveals more structured interpretation than the interface exposes. The text field remains editable, but there are no direct date/place corrections. | Add a compact editable interpretation with explicit Update Search. This needs a validated API contract, not just chips that prepend natural-language text. Keep old versus refreshed Posters unmistakable. |
| Medium | Home spends too much height explaining a simple action | At 390px, Home is about 1855px tall in the captured DOM. The three stacked instruction panels separate the Search from Taste onboarding. The visual hierarchy gives “Try one of these” more emphasis than its role requires. | Short product promise, one input, two or three quiet examples. Reduce “How it works” to short supporting copy or an optional disclosure. Put Taste within easy reach. |
| Medium | Current Taste onboarding privileges a restricted path | Observed prominent Spotify button and collapsed alternatives. Copy correctly says invited accounts, but most public portfolio visitors cannot use that path. | Make manual Artist entry immediately available to everyone; retain Spotify as an obvious invited-account option. Keep its shelf separate from model-powered Search. This intentionally revises the earlier Spotify-first design choice. |
| Medium | Navigation hides the two most useful destinations | Home has an icon-only Menu. Saved has a brand link and, in the observed state, no equivalent menu. | Visible Saved count and Your Taste at desktop; concise text labels on mobile where they fit. Preserve navigation and active Search when opening panels. |
| Medium | Save/Skip is expressive but needs recovery | Observed Save advances to another Ticket. Source stores the decision and provides a notice, but no immediate Undo control. | Add Undo with a clear return to the prior selection. Keep explicit Save/Skip buttons; drag remains optional. Test rapid repeated actions and persistence failures. |
| Medium | Empty state tells people how to recover but makes them do the editing | Observed “Try wider dates or a nearby city” without direct controls. | Offer Edit dates / Change place, reflecting actual interpreted fields. Never silently widen a Search or promise a nearby alternative the source has not returned. |
| Medium | Five typefaces fragment the hierarchy | Source: Anton, Bricolage, Big Shoulders, Hanken and Doto. The display face is effective; the whole set is a lot for a compact product. | First concept uses Anton and Bricolage. Test whether Doto belongs as a very small brand accent; avoid it for essential dates/prices. Font count alone is not a measured performance finding. |

## Motion: keep continuity, remove waiting

The present reveal has real event-driven semantics, which is good. However, its choreography begins after Recommendations are already available. Source timing for eight picks allows up to 768ms of name reveal (24 names), 550ms picks pause, 1980ms glide/grow, then a 420ms Ticket entrance. That is roughly 3.3 seconds to begin the Ticket stage and 3.7 seconds to settle, depending on event timing. This is calculated from code, not a stopwatch measurement. A two-pick reveal is shorter.

The reference-research agent recommends retaining the existing timing because the current spec prescribes it. I disagree for the proposed redesign: the user explicitly asked to rethink the experience. Keep the approved timing in production until a spec change is reviewed, but test a much shorter arrival that never gates the actionable Ticket. Preserving the identity does not require preserving this delay.

Suggested targets, to test rather than call standards:

- Instant input and focus response; no animated label while typing.
- 120–180ms icon or saved-state feedback.
- 180–250ms Search-shell or panel transition; interruptible.
- 200–300ms Ticket selection transition, with content/actions available immediately.
- One small optional signature reveal on first entry, never continuously behind reading.
- Reduced motion: direct state changes, all status and controls retained.

Use the existing Motion/Base UI stack where useful. Do not import another animation library merely to signal modernity. Keep clipping decorative, preserve focus and layout, and profile real devices before claiming 60fps.

## Proposed direction: a quiet surface with a festival voice

A separate interactive concept tested this structure before a production rewrite. It was superseded by `docs/mocks/fluid-search/` and deleted.

- Palette: ink `#10291F`, pale green `#F4F6F0`, signature orange `#FF5A1F`, Ticket pink `#FFD3E4`, soft green `#E7EDE4`, line `#D6DED5`.
- Typography: Anton for the characteristic identity and Artist names; Bricolage for everything a person reads and operates.
- Layout: left-aligned Search and facts, a compact Poster selector, a Ticket whose actions belong inside its surface.
- Motion: stable Search surface, short view transitions, small status activity only while a demo run is active. No perpetual sun.
- Alternative: the same structure on a solid orange field. The toggle isolates the palette decision from the layout decision. It is not a second complete design direction.

The prototype includes Home, demo Search progress, Poster selection, Save/Undo, Saved removal, editable place/date fields, Taste entry, empty/error recovery, and a reduced-motion path. Its fonts are embedded, and it works as a standalone file with no network calls. It contains fictional fixture Concerts; refinements change controls but do not search or rerank real data. Saves last only for that page session. Spotify and purchases are intentionally represented as explanatory controls, not fake working integrations.

This is a testable concept, not a finished redesign. The hero is quieter but risks becoming less distinct than the original; the small sun and Anton need to carry enough identity. The horizontal mobile selector needs testing with eight long Artist names. Focus after replacing Ticket markup needs production-grade handling. A more ambitious shared-element morph should only be added if it improves orientation in that test.

## Recommended implementation order

1. **Hierarchy and surfaces:** quiet working background, compact Home guidance, coherent navigation, facts/actions inside Ticket. Preserve all existing data and storage contracts.
2. **Recovery:** Undo Save/Skip; clear empty/error editing paths. Verify keyboard focus and reload persistence.
3. **Correctable Search:** structured interpretation editing and explicit rerun, with contract tests for precedence, date scope and stale-stream isolation.
4. **Motion:** replace post-result presentation waiting with a short arrival; update interface spec and browser tests deliberately.
5. **Return visits:** explicit opt-in Saved Searches and calendar export, only after source-date/timezone handling is correct. No silent history capture, invented start time, new accounts or notification service required for this initial direction.

Success should be judged by task outcomes: can a new visitor submit a valid Search, identify date/place/source, correct a mistaken city, save a Concert, undo a mistake and retrieve it? Compare current and proposed UI with the same tasks. Record task success, wrong turns, time-to-action and qualitative preference; do not declare a conversion or satisfaction improvement from this visual study.

## Validation of the concept

Local Chromium checks passed at 1280×844 and 390×844: Search completion, refinement, Save/Undo, Saved removal, empty/error states, dialog Escape, stop during reduced-motion mode, and no horizontal overflow or page JavaScript errors. Screenshots were captured after transitions settled. Tests and capture scripts are retained in the evidence folder; their dependency paths refer to this machine. These checks validate prototype interactions, not source integration, relevance, physical-device motion, screen-reader behavior, or production focus management.

## Research and constraints

See [fluid reference research](2026-11-07-fluid-ui-references.md) for the four named sites and implementation sources, and [agentic Search UX research](2026-11-07-agentic-search-ux.md) for HAX, PAIR, Fluent and accessibility guidance. Source facts stay outside the LLM, Spotify account data stays outside the Search pipeline, and missing facts remain absent. The proposed visual changes intentionally differ from parts of `04-interface.md`; no current spec or production implementation was silently rewritten.
