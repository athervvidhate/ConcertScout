# Motion reference study, 7 November 2026

Observed in desktop preview at 1402 × 877, with scrolling, clicks and observations separated by time. These are design references, not measurements of their exact durations or implementation.

## Ardia

- **Observed:** Its first screen is a painterly landscape with enormous condensed type and a sun; the page itself invites “Drag the sun.” The visual idea is coherent with its “Touch grass” proposition. The sun is specific to that idea, not a transferable concert motif. I did not verify the drag response.
- **Observed:** Scrolling one screen reveals a framed, interactive browser rather than a static product illustration. The fixed header stays visible. At one observation the demo showed a React page; after clicking a sidebar item it changed to a graceful fallback explaining the selected site cannot load in an embed. The callout changed from “Go on, click a tab” to “Told you.” Its frame and setting remain stable while the content changes.
- **Interpretation:** Character comes from a strong world around a functional demonstration, then responsive feedback establishes that the product is real. The frame gives state changes a stable spatial anchor. Avoid copying the landscape, sun, or fake-control limitation.

## ID4

- **Observed:** The hero uses a restrained near-black field with big central type, a single bright download control, and a large product demonstration. Across time-separated observations the supported service in the sentence changed from YouTube to Reddit; the longer feature sentence also cycled terms. This was autonomous rather than a response to my click.
- **Observed:** After scrolling, the header condensed into a centered floating capsule. Product feature examples sit in different-sized regions. The format example changed over time, and clicking Transcript explicitly switched the selected tab, waveform preview to transcript lines, and filename/metadata to a text file. Elsewhere, the download list changed from sizes to completed checkmarks between observations. Thus action and status alter multiple related details together, while the surrounding layout stays stable.
- **Interpretation:** This is choreography of meaningful state, not constant ornamental movement. Cycling examples can communicate range, but concert facts must never cycle into invented values. Selected, pending and complete should be causally connected to real actions or real progress.

## X article

The [article by seeco](https://x.com/seeconvm/status/2106096193235259564) was accessible in the page's accessibility tree, although the visual page presented a sign-in prompt below its opening. It discusses deliberately specified visual references, a state list, springs with mass, and review of rendered frames. Its frame-by-frame seek approach is described for producing video, not as a prescription for an interactive app. Treat its model-specific claims as the author's claims, not verified facts. The practical takeaway for this brief is to write a concrete motion score and review the full sequence rather than assume a still frame demonstrates quality.

## Four distinct concert-discovery directions to explore

1. **Venue doors:** deep burgundy, worn-ticket ivory, warm amber; narrow venue-poster typography. The search area feels like a venue entrance: submitting opens a single set of doors or folds the search panel aside to reveal the actual results. Event rows expand in place, preserving their date and venue anchors. One opening gesture carries the drama; no ongoing ambient animation.
2. **Record shop:** saturated cobalt, orange-red, paper white; large sans with tactile sleeve art. Artist selections act like pulling records from a crate: a focused selection slides forward and returns smoothly, with a clear selected state. Search transitions to an ordered stack of show listings, not decorative album covers posing as data.
3. **Marquee:** midnight blue, electric violet, bright warm white; a confident wide display face. A single scanning band resolves into a live search status, then stops when actual results arrive. Show details unfold directly from the selected row; no simulated progress percentage or invented discoveries.
4. **After the encore:** near-black plum, hot coral, soft lavender; expressive oversized artist typography and real event imagery where licensed. Result arrival is a short rhythmic sequence: the heading settles first, then a few actual results enter together with small offsets. A selected show opens like a program sheet; the remaining list stays visible for context.

## Motion and interaction principles

- Define explicit states and triggers: idle → submitted → real loading → results/empty/error; show details open/close. Give each transition a start, destination, and interruption behavior. Motion reinforces actual state and never fabricates event facts or completion.
- Use transform and opacity for brief transitions where practical; avoid layout thrash and preserve anchors, keyboard focus, and readable results. Tune timing by viewing the real sequence, not by a static screenshot. Avoid forcing delay after results are ready.
- Respect reduced-motion preferences with immediate or minimal transitions. Make controls keyboard and touch operable; test rapid input and a narrow viewport. Keep autonomous motion limited and ensure it does not obstruct content.
- These are proposed design ideas, not observed site behaviors. Duration, easing, artwork, and identity require prototyping and user review.
