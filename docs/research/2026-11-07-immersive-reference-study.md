# Immersive motion reference study — 7 November 2026

Observed in the public desktop pages at 1402 × 876. These are recorded behaviors, not claims about the sites’ implementation. Scrolltide’s public library clips are muted previews; I did not open premium templates or continue through its signup flow.

## Scrolltide — public library previews

**Observed:** The library cards contain video previews that begin playing as the cards enter the viewport. Their imagery advances while the card frame and title stay put. At separate observations, Murk showed a koi shifting through a rippling pond; Tinta House rearranged its editorial print collage; The Long Light moved from a closed, flat cover to a tilted/open book view. This gives each card a small window into a different visual world without making the catalog itself move around.

**Observed:** The previews loop. For example, Murk’s playback time advanced and then returned near the beginning between observations; the card remained in place. A compact format/technology strip above the library also travels horizontally while the navigation stays fixed.

**Design use:** Treat any atmospheric motion as a viewport-contained preview and keep event discovery controls/results spatially steady. A sound-wave or liquid-light surface can react inside the search/results frame, then settle when real results arrive. Do not let ambient motion reorder or obscure event details. This is an application to Concert Scout, not behavior observed on Scrolltide.

## BeautifulUI — working component demos

**Observed:** Loading State displays an elapsed-seconds value beside “Churning,” and offers Drive, Dots, Orbit, and Surfer controls. The elapsed value changed between observations (5.7s, 21.1s, 46.6s); selecting Dots changed the selected control. The demo communicates ongoing work with a small pixel-like indicator and elapsed time rather than taking over the panel.

**Observed:** Thinking starts as a concise “Thought for 4 seconds” disclosure. Opening it reveals a vertical list of completed steps. Its Steps/Reasoning/Search/Coding switch changes the content in the same bounded component: Search showed a query with source rows, while the Steps state showed a short checklist. The surrounding demo frame and page layout remain stable.

**Observed:** The Search demo filters as text is typed. Entering “cold” immediately reduced five command rows to “Check cold-chain status,” keeping the input and result inside the same panel. This is the clearest fit for a search-first concert interface: the content responds in place and preserves the user’s visual anchor.

**Design use:** Keep the main search/results surface fixed; swap its contents across explicit idle, searching, results, empty, error, and expanded-show states. If a loader is needed, show actual elapsed time or a subtle state label and stop as soon as results are ready. Preserve useful anchors and expose the same state change with keyboard focus. These are recommendations, not claims about the reference’s accessibility behavior.

## Three visual directions for Concert Scout

### 1. Soundcheck, seen through a ripple

Build a deep blue-black room with a dimensional, layered interference field: broad soft rings and fine contour lines shift only around the active search focus. Typing a city or artist gently draws the field toward the search point; results settle into a clear vertical schedule, with the field reduced to a still edge treatment. Selecting a show opens its detail sheet in the same frame. Use restrained venue-light colors for result cues, not a full neon gradient wash. The dramatic visual is the light field; date, venue, price, and source remain plain and stable.

### 2. The room before doors

Give the page a dark stage architecture with two tall translucent scrims around a centered search console. Submitting folds the scrims aside to reveal actual listings; filters narrow the list in place, and a selected result pushes a single event panel forward while the list remains visible. A narrow band of moving light can track the active filter, then stop when filtering finishes. This makes the interaction memorable without fake loading or fabricated event facts.

### 3. A setlist made of folded light

Use a near-black plum base and an abstract lamellar field: thin, overlapping planes catch a soft, directional glow and shift a few degrees with pointer movement. Search remains the dominant, persistent control. Results appear as a precise setlist with date and venue alignment; opening one concert unfolds a paper-thin detail layer from its row and closing it returns focus to that row. Keep plane motion short, local, and disabled or flattened under reduced motion. The dimensional sculpture supplies portfolio character; the event rows carry the functional weight.

## Practical motion score

- Idle: one slow, low-contrast ambient surface, with no competing text animation.
- Focus/type: local surface responds to the query point; suggestion list filters immediately.
- Submit: show a real searching state only while the request is pending; do not add a theatrical delay.
- Results: keep the search anchor; reveal the returned rows together or in one brief grouped arrival.
- Details: expand from the chosen row and return focus to that row on close.
- Empty/error: use a quiet, legible state inside the same search/results frame.
- Reduced motion: remove continuous drift and use immediate state changes or simple opacity.

The three directions and motion score are proposals. No Concert Scout code or prototype was changed in this study.
