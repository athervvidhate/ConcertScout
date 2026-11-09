# Agentic Search UX research for Concert Scout

**Date:** 2026-11-07  
**Scope:** Research and product design recommendations only. No implementation or deployment changes.  
**Product snapshot inspected:** `b8015c5104b182cad68e1b07f3ccf9a2f377c9c8` (`concertscout-app-primary`, read-only; clean at inspection). The branch had advanced from `7d779c9` during inspection; its intervening changes did not alter the Search/Poster components examined.

## Executive recommendation

Keep Concert Scout a search product. Give the person a small set of direct controls around one Search: correct what the interpreter heard, see what is happening in truthful terms, stop a run with honest cancellation semantics, understand which facts come from Ticketmaster versus which part is a fit judgment, refine the Search, and optionally save a Search recipe for later.

A fluid interface can make these states feel connected without turning the pipeline into a chat transcript: one Search surface can tighten into an editable interpretation, show real phase updates, then resolve into the Poster and Tickets. Preserve the festival-poster typography and color where contrast and legibility hold. Use motion to show continuity and state change, not as a proxy for work or intelligence. Avoid an “agent activity” console, decorative confidence meters, model avatars, and new interaction surfaces that don’t help someone find, judge, or return to a Concert.

## Evidence labels and inspection limits

- **Source-inspected** means read in the product files/specs at the commit above.
- **Observed** is reserved for a state directly seen in a running UI. No running page was inspected in this task.
- **Inference** is a conclusion from source code or documentation, not a claim about live behavior.
- **Proposed** means a design opportunity, not an existing feature.

The T3 preview controls were unavailable and CUA reported that its browser host was unavailable. The named reference pages [Polyviral](https://polyviral.org/id4/), [Jam](https://jam.dev/mac), [Board UI](https://www.boardui.com/), and [React Bits](https://reactbits.dev/) were therefore not inspected. Their names are treated only as inspiration supplied in the task; no specific visual or interaction pattern is attributed to them here.

## Guidance from primary sources

1. **Microsoft HAX Toolkit** asks teams to support efficient dismissal and correction, scope service when intent is uncertain, explain why an output occurred, encourage granular feedback, and convey consequences of user actions. For Search, this favors compact correction and recovery controls over a verbose account of model internals. HAX also cautions that an explanation can inflate trust and expectations, so the explanation should be useful and appropriately bounded. [HAX Guidelines](https://www.microsoft.com/en-us/haxtoolkit/ai-guidelines/), [efficient correction and scope when uncertain](https://www.microsoft.com/en-us/haxtoolkit/card-test/), [why the system did what it did](https://www.microsoft.com/en-us/haxtoolkit/guideline/make-clear-why-the-system-did-what-it-did/)

2. **Google PAIR’s People + AI Guidebook** centers user needs, mental models, explainability and trust, feedback and control, and graceful failure. Its explainability guidance recommends optimizing for understanding and using partial explanations where a full explanation is unavailable; it also notes that displaying confidence can influence decisions. Concert Scout should show what it can substantiate and avoid an uncalibrated “match confidence” number. [Guidebook chapters](https://pair.withgoogle.com/guidebook-v2/chapters), [Explainability + Trust](https://pair.withgoogle.com/guidebook-v2/chapter/explainability-trust/), [Errors + Graceful Failure](https://pair.withgoogle.com/guidebook-v2/chapter/errors-graceful-failure/)

3. **Microsoft Fluent 2 Responsible AI** frames transparency, user agency, scoped communication, and harm reduction as UI concerns. Its wait guidance says to use descriptive status labels and reserve determinate progress bars for work whose progress is actually trackable. This supports the existing event-driven phase text and argues against percentages derived from elapsed time. [Responsible AI](https://fluent2.microsoft.design/responsible-AI), [Wait UX](https://fluent2.microsoft.design/wait-ux)

4. **W3C WCAG 2.2** requires status messages to be programmatically determinable without moving focus (4.1.3, AA), visible keyboard focus (2.4.7, AA), and minimum target size of 24 by 24 CSS pixels (2.5.8, AA, subject to exceptions); the 44 by 44 enhanced target criterion is AAA (2.5.5). The current interface spec’s 44px touch target is a useful product standard. Preserve live status semantics, focus visibility, keyboard operation, reduced motion, and adequate target sizes as controls are added. [WCAG 2.2](https://www.w3.org/TR/WCAG22/), [Understanding Status Messages](https://www.w3.org/WAI/WCAG21/Understanding/status-messages)

## Current product baseline

### Source-inspected

- Search is deliberately non-chat. One text field accepts Taste, place, and optional dates; imported Taste can fill what the text leaves open. A typed place takes precedence over shared location.
- The API streams real `status`, `interpreted`, `candidates`, `poster`, `elsewhere`, `error`, and `done` events. Status text and candidate count are not simulated progress.
- The interface shows a formatted interpretation after the response arrives. It does not currently expose controls to edit that structured interpretation.
- The in-flight Search button is disabled. The frontend has an `AbortController` and aborts when a Search is cleared or replaced, but the visible Search surface has no explicit Stop/Cancel control.
- The Poster reports a pick count and candidate count, then opens one Ticket at a time. Save and Skip are buttons, also available through drag; Saved Concerts persist in browser local storage. A dropped stream can be retried.
- A Ticket’s reason is a ranking explanation. Date, venue, time, price, image, and ticket URL are filled from the Ticketmaster source record; absent source fields are omitted. Ticket facts currently have a ticket link but no visible “listed by Ticketmaster” attribution or source freshness timestamp.
- The Search interpretation event contains recognized place, region/radius, date range, Artists, and genres. It does not expose a confidence score or alternatives.
- The pipeline’s model calls interpret the text and rank a shortlist. The model does not supply Concert facts. Spotify-account data uses a separate shelf and must not enter model prompts. Coordinates do not reach a model.

### Inference

- Presenting the interpretation as a compact editable summary is a high-value control point: it can catch a wrong city, date, or Artist before the person invests in reviewing Tickets.
- “Cancel” is a promise about backend work, not merely closing a panel. The browser’s request abort is visible in source, but I did not verify whether every in-flight provider call and child task reliably stops or whether aborting prevents model spend. Do not label a client-side disconnect “Search cancelled” until server cancellation and cost semantics are verified.
- A model-written fit reason may sound more certain or evidential than the underlying ranking warrants. The current pipeline does not return calibrated confidence or a structured explanation trace. Avoid percentages and claims of certainty.
- A last-checked timestamp is only trustworthy if the backend carries the source/cache retrieval time through to the Ticket. It must not be inferred from the browser response time.

## Ranked feature opportunities

Effort is relative: **S** small, **M** medium, **L** large. Benefits describe expected user value, not measured outcomes.

| Rank | Opportunity and user benefit | Evidence / effort | Constraints | Acceptance criteria |
|---|---|---|---|---|
| **1** | **Editable interpretation before committing to the Poster.** Show recognized Taste, place/Region, and date range as a concise “We read this as…” summary. Let a person correct a field and rerun without reconstructing the sentence. This catches costly, high-impact interpretation errors early. | HAX correction/scope; PAIR control and graceful failure. **M–L**, because the current request contract accepts text and the server owns interpretation. | Keep typed place precedence and “near you” behavior explicit. Do not fabricate missing dates. Preserve original request text for retry only while the current Search is on screen. If corrections become structured input, validate it server-side and keep source facts outside the LLM. | Given an interpreted Search, each displayed field can be edited by keyboard and touch. Blank dates remain blank. “Update Search” clearly starts a new run; stale results are not presented as current. If interpretation is incomplete, the person can correct it before spending another model request. Assistive technology announces the updated interpretation without stealing focus. |
| **2** | **Honest stop / cancellation and recovery.** Give a visible “Stop waiting” or “Cancel Search” action during a run, plus a clear state after stopping and a one-action way to edit or retry. This gives control during a long or irrelevant Search. | HAX dismissal/correction; PAIR graceful failure; WCAG operability. **M–L** depending on end-to-end cancellation guarantees. | First establish whether abort cancels the server task, upstream requests, and billable model work. If it only closes the browser stream, label it “Stop showing progress” or state plainly that work may continue. Handle the known risk of orphaned gather tasks. Never imply refunded or avoided cost without evidence. | User can stop the visible run by keyboard/touch. Focus remains predictable. The terminal message accurately distinguishes stopped client stream from server-confirmed cancellation. A cancelled/stopped run cannot later overwrite a newer Poster. Reduced-motion and screen-reader states stay understandable. |
| **3** | **Separate “why it fits” from listing facts, with visible source attribution.** Keep one short reason near the Artist, and label ticket details as Ticketmaster listing information with an outbound source link. This helps people evaluate recommendations without confusing model judgment with event facts. | HAX explanation caution; PAIR partial explanations; ADR 0002. **M**. | Do not expose chain-of-thought or invent evidence. Reasons must be evaluated against the actual match signal. Do not add source timestamps until the API reports authoritative retrieval/cache time. A missing time or price remains missing. Spotify-account data is not a source for the LLM reason. | Each Ticket visually distinguishes recommendation reason from date/place/price facts. Ticket facts link to their source record and are labeled as source-reported. No confidence percentage appears unless calibrated and validated. Missing source fields remain absent. Reasons are phrased as a fit judgment, not a verified concert fact. |
| **4** | **Refine this Search from the Poster.** Offer a few direct adjustments such as “wider dates,” “change place,” or “more like [Artist]” while keeping the Search editable. This lowers the cost of recovery from an empty or weak Poster. | HAX correction and efficient invocation; PAIR control and user needs. **M**. | Suggestions must derive from current structured fields and be visible as choices, not invented “agent next steps.” Re-running costs network/model calls and consumes the visitor’s limit; make the action clear. Keep “elsewhere” distinct from a result in the requested city. | From an empty Poster, a person can select an offered refinement, inspect the changed Search, and confirm it before rerun. The original Search remains recoverable. Refined place/date/Taste are reflected in the interpreted summary. No refinement silently broadens location or dates. |
| **5** | **Save and return to a Search recipe.** Let a person explicitly save a Search they want to repeat, then reopen it from a small Saved Searches area. This complements Saved Concerts, which retain individual Concerts. | HAX control and consequences; product already stores Saved Concerts locally. **M**. | Start with explicit opt-in and device-local storage. Do not silently retain all Search text or coordinates. Do not store Spotify shelf contents, account data, access tokens, or derived profile. Explain that a saved Search is a recipe and its next Poster may differ because Ticketmaster listings change. | “Save this Search” is explicit and distinct from Save Concert. A saved recipe contains only fields the person can inspect before saving, is editable/removable, and survives navigation/reload on that device. No Spotify-account data or coordinates are included by default. Reopening runs a fresh Search and does not imply the old Poster is current. |

## Low-value complexity to avoid

- **Fake percentages, “thinking” timers, and decorative agent activity.** They cannot be derived from real milestones; the product spec explicitly says progress is real and forbids invented percentages. Show the actual stage and, when available, actual candidate counts.
- **Confidence rings or match scores on each Ticket.** There is no calibration evidence or confidence field in the current contract. A numeric value would look authoritative without being decision-useful. Prefer a bounded reason tied to available match evidence.
- **A chat panel, agent avatar, tool-call transcript, or “ask the agent” follow-up.** These add another interaction model to a product whose deliberate shape is Search, and they do not solve the current high-value correction gap.
- **Automatic personalization from Save/Skip.** Save and Skip are local decisions today, not permission to build a taste profile or retrain. HAX says to explain consequences of feedback. If future learning is considered, make it explicit, reviewable, reversible, and separate from Spotify account data.
- **Persistent Search history by default.** Free-text Taste can be personal. A short explicit Save Search action is easier to understand than silently retaining every Search.
- **More animation solely to make the product feel “agentic.”** Keep the existing poster reveal if it remains legible, quick, and motion-accessible. State changes should remain immediate and functionally clear under reduced motion.

## Source and privacy boundaries for design

- Preserve [ADR 0002](../adr/0002-facts-never-pass-through-the-llm.md): Concert names, dates, venues, prices, images, and URLs must come from the source record. A visual explanation cannot turn model prose into an event fact.
- Preserve [ADR 0003](../adr/0003-official-spotify-access-only.md): Spotify-account data never reaches an LLM. Keep the Spotify shelf and any future Saved Search separate; do not use account contents to build LLM prompts, explanations, or persistent history.
- Preserve the existing contract that coordinates never reach a model and are requested from the browser only after the person chooses location sharing.
- Keep feedback/report data boundaries intact. Do not add coordinates or Spotify data to reports, analytics, or saved recipes.
- Do not treat a cache timestamp as a source update time. If showing freshness later, define whether it means “retrieved by this service” or “updated by the source,” and label it accordingly.

## References

- Microsoft, [Guidelines for Human-AI Interaction](https://www.microsoft.com/en-us/haxtoolkit/ai-guidelines/)
- Microsoft, [HAX Toolkit card test and guideline index](https://www.microsoft.com/en-us/haxtoolkit/card-test/)
- Microsoft, [Guideline 11: Make clear why the system did what it did](https://www.microsoft.com/en-us/haxtoolkit/guideline/make-clear-why-the-system-did-what-it-did/)
- Google PAIR, [People + AI Guidebook chapters](https://pair.withgoogle.com/guidebook-v2/chapters)
- Google PAIR, [Explainability + Trust](https://pair.withgoogle.com/guidebook-v2/chapter/explainability-trust/)
- Google PAIR, [Errors + Graceful Failure](https://pair.withgoogle.com/guidebook-v2/chapter/errors-failing/)
- Microsoft Fluent 2, [Responsible AI](https://fluent2.microsoft.design/responsible-AI)
- Microsoft Fluent 2, [Wait UX](https://fluent2.microsoft.design/wait-ux)
- W3C, [Web Content Accessibility Guidelines (WCAG) 2.2](https://www.w3.org/TR/WCAG22/)
- W3C WAI, [Understanding Success Criterion 4.1.3: Status Messages](https://www.w3.org/WAI/WCAG21/Understanding/status-messages)
