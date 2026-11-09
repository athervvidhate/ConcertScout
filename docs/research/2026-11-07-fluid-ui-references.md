# Fluid UI reference research

Research checkpoint: 2026-11-06 (Pacific). Scope: design advice only. The reference URLs are marketing sites or component showcases, not evidence of their products' daily behavior. Browser inspection consisted of desktop page snapshots; interaction timing, mobile behavior, and motion were not directly tested. Consequently, the recommendations below are hypotheses, not measured findings.

## Evidence and context

- **Observed:** [ID4](https://polyviral.org/id4/) presents a single prominent download action, a changing platform example, and compact feature demonstrations including Video, Audio and Transcript controls. Its feature examples illustrate capabilities, not a tested production workflow.
- **Observed:** [Jam for Mac](https://jam.dev/mac) places a prominent download action and video under a large headline whose accessible tree contains multiple words in the same headline slot. It pairs product visuals with explanatory text. A snapshot alone does not establish how the words animate or whether the actual app behaves similarly.
- **Observed:** [BoardUI](https://www.boardui.com/) presents a large headline, a clipped horizontal widget showcase, and compact labels paired with values. The showcase extends beyond the viewport. These are marketing examples, not evidence of working dashboard interactions.
- **Observed:** [React Bits](https://reactbits.dev/) demonstrates a visual alongside code, named sliders, and a preset radio group. It showcases expressive animation; its homepage is not a recommendation to add every effect to a product.
- **Source-inspected:** the supplied current worktree was at `f1defa4f65b284077283597e8848769dbc46ee05`, on `polish-home-and-listings`, with a modified e2e file. `search.tsx` replaces home content during a Search, uses example placeholders and disables submission while searching; `poster.tsx` uses Motion and checks reduced motion. These are source observations, not a live product audit. The specified branch name differed from the actual checkout.
- **Source-inspected:** the interface spec establishes the poster identity, playful type, real SSE status, prescribed fly-in, 44px touch targets and reduced-motion behavior. Its animation timing is a contract, not a blank canvas. ADR 0002 requires source-derived Concert facts; ADR 0003 keeps Spotify data from the LLM.

## Keep / adapt / reject

| Pattern | Decision | Application and critique |
|---|---|---|
| One dominant action, supporting information subordinate | Keep | Make Search visually immediate; retain explicit labels and example Searches. ID4's download hierarchy transfers without its download funnel. |
| A container changing between entry and work states | Adapt | Explore a small, stable Search shell that compacts after submission, keeping input, focus and status legible. Avoid a spectacular full-screen morph that delays access or moves the user's typing target. This is a proposal, not an observed reference implementation. |
| Text and icon changes | Adapt | Use a brief crossfade or swap for a real state change, with one accessible name and no repeated live announcements. Rotating marketing headlines are distracting in a frequently used Search. Preserve the spec's static reduced-motion example. |
| Compact labels and values | Keep | Use BoardUI's hierarchy as inspiration for Ticket facts, keeping Artist, date, venue and action distinct. Never infer missing price or time. |
| Clipped showcase edges | Reject for controls | Decorative imagery may crop, but interactive controls, focus rings, labels and hit areas must stay visible. A partial next Ticket must not be the only cue that more content exists. |
| Playful typography | Keep | Existing Bricolage, Anton, Big Shoulders and Doto are an intentional poster voice. Reserve display styles for hierarchy; favor readable body text and tabular numbers for facts. |
| Tunable live controls | Adapt | React Bits' labeled controls and presets suggest immediate, visible feedback; apply this to direct user choices only, without blocking typing on animation or network. |
| Perpetual text cycles, parallax, WebGL backgrounds | Reject in core workflow | Marketing spectacle competes with repeated use; the interface spec explicitly excludes WebGL backgrounds. Real status and actual Recommendations deserve attention. |
| Choreographed Poster reveal | Keep as specified | It conveys a Search's transition to a Poster, but only from actual events and candidates. Do not add staging or fabricated progress. |

## Proposed motion budget

These are design targets for future review, not measured performance or a replacement for the approved spec.

- Input, focus, selection and enabled/disabled state: immediate; decorative feedback can settle in 100–150 ms, without throttling keystrokes.
- Small icon or label swap: 120–180 ms; keep a stable accessible label and avoid clipped focus outlines.
- Search shell compaction or panel transition: 180–250 ms, interruptible; no required action waits for the animation. Test responsive layouts before committing to a shared-element morph.
- Ticket state change: 150–250 ms; preserve explicit Saved/Skipped text and non-color indicators. Drag must retain a button/keyboard alternative.
- Poster reveal: retain the interface spec's 550 ms readable picks, 750 ms glide with 100 ms stagger, 80 ms rest and 450 ms grow. Do not stack an additional shell animation over the reveal. Reduced motion shows the Poster directly.
- Continuous movement: none added to work surfaces. Honor the spec's reduced-motion handling for existing sun, equalizer and example text.

## Implementation and validation implications

[Motion layout animations](https://motion.dev/docs/react-layout-animations) can interpolate layout via transforms and support shared elements; nested scaling and text distortion must be checked, not assumed away. Use this only where continuity improves orientation. [Motion accessibility](https://motion.dev/docs/react-accessibility) explains `MotionConfig reducedMotion="user"` and `useReducedMotion`; CSS and Web Animations API effects require their own handling. [Base UI animation guidance](https://base-ui.com/react/handbook/animation) is relevant to keeping a dismissing popup mounted until its exit completes; preserve its focus and keyboard behavior instead of replacing controls with decorative divs.

[web.dev's animation guide](https://web.dev/articles/animations-guide) recommends preferring transform and opacity and profiling paint, with `will-change` used sparingly. Test with performance traces on modest devices, at 390px and 1280px, with reduced motion, keyboard focus, screen readers and rapid repeated input. Verify no layout shift obscures controls or delays input. [W3C's interaction animation guidance](https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions) explains disabling nonessential motion (WCAG 2.3.3, AAA); the project's own reduced-motion specification applies regardless of conformance level.

Open questions for a live product review: whether compaction actually improves orientation, whether text or icons clip at narrow widths, whether focus survives state changes, and whether repeated searches feel faster. These require interaction tests; they cannot be settled from the snapshots above.
