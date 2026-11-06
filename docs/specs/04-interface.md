# Interface

The old UI looked generated, so the rebuild has a real point of view: a screen-printed festival poster on a hot orange field. Decoration must help someone find a Concert. Anything that exists for its own sake goes.

Follow `ui-skills.com` rules and Emil Kowalski's motion rules. Use coss ui (Base UI) for controls. The fly-in uses the Web Animations API, and Ticket drag uses Motion. Short React Bits text effects are allowed. WebGL backgrounds are not.

## Tokens

| Token | Value |
|---|---|
| Field | `#FF5A1F` |
| Field stripe | `#FF7A1F` |
| Ink | `#10291F` |
| Pink | `#FFD3E4` |
| Ticket colors | `#F7C5D5`, `#F6E27A`, `#A7DCE2`, `#F4C27A`, `#D9E7A1` |
| Ticket text | `#1A1A18` |

The sun is a `repeating-conic-gradient` of 7.5 degree stripes that rotates once every 90 seconds.

## Type

| Use | Font |
|---|---|
| Poster names | Anton 400, which matches the owner's reference image |
| UI | Bricolage Grotesque, variable |
| Ticket Artist | Big Shoulders Display 800 |
| Ticket date and price | Doto 800 |
| Body and status | Hanken Grotesk |

Poster sizes:

| Tier | Size | Weight |
|---|---|---|
| Headliner | `clamp(52px, 11.7vw, 164px)` | 400 |
| Second tier | `clamp(34px, 7.4vw, 104px)` | 400 |
| Third tier | `clamp(24px, 3.8vw, 54px)` | 400 |

Above 700px wide, each size also shrinks with the viewport height, so the Poster and Ticket fit an ordinary laptop screen. A headliner too long for its row shrinks to fit.

Load fonts with `next/font`. Use tabular numbers for dates and prices.

## The loader: Fine print

Nothing on screen is a fake. No skeleton blocks, no invented progress percentages. Each stage runs on real SSE events.

| Stage | Trigger | What shows |
|---|---|---|
| 1. Opening | Submit | Equalizer bars in the Poster area, status "Reading your request", then each real `status` message. Keep this short: send `candidates` as early as possible, aiming for under 2s |
| 2. Names | `candidates` | Equalizer leaves. Real candidate names fade in as small print, 32ms apart, up to 38 names |
| 3. Ranking | Same event | Names stay. Status shows real counts |
| 4. Picks | `poster` | Picks turn pink, the status changes to "8 picks from 38 close matches", and other names fade together over 0.28s |
| 5. Fly-in | 550ms after picks turn pink, so the status can be read | See below |
| 6. Ticket | As soon as the fly-in ends | First Ticket rises 12px over 420ms. The headliner stays pink |

Stages 4 to 6 are presentation only. Every Recommendation already exists when the `poster` event arrives, so nothing after it waits on the network. The 550ms before the fly-in exists only so the status can be read, and no other pause is allowed.

Save and Skip stay hidden until stage 6. If the `poster` event arrives before stage 2 finishes, stage 2 completes first.

### Fly-in

Names must never feel rushed. Growing while travelling caused the collisions, so the fly-in has two separate steps.

| Value | Setting |
|---|---|
| Glide duration | 750ms per name |
| Start gap | 100ms, headliner first, in rank order |
| Glide easing | `cubic-bezier(.65, 0, .35, 1)` |
| Rest | 80ms after the last name lands |
| Grow duration | 450ms, all names together |
| Grow easing | `cubic-bezier(.22, .61, .36, 1)` |
| Total | 1,980ms |

1. Each name glides to the center of its final spot at small size. Using ease-in-out means it starts and stops softly.
2. Once every name has landed, all of them grow together.

Each name scales up inside its own final box during the grow step, so names cannot touch there. The owner shortened the first version, 2,890ms long, because it felt slow. The shorter start gap lets small names cross a little more often during the glide.

To avoid stutter, keep the animation on the compositor:

- Animate only `transform` and `opacity`. Animating `color` in the same animation moves the whole thing to the main thread.
- Render each name at full size with `will-change: transform`, then scale it down. This keeps the text sharp as it grows.
- Stack a pink copy over the ink name and fade its opacity during the grow step, rather than animating color. The headliner stays pink.
- Read FLIP positions from the DOM once, before the animation starts, and remove `will-change` when it ends.

### Reduced motion

With `prefers-reduced-motion`, the sun and equalizer stop, there is no fly-in, and the Poster appears directly. Status text stays, and it is an `aria-live` region.

## Interaction

- Ticket drag uses Motion and needs real device testing. The mock never tested it.
- Saved and skipped states work without color alone: underline plus a "saved" label, and strikethrough.
- All targets are at least 44px on touch screens.
- Check at 390px and 1280px wide.
- Pink on orange is below 4.5:1 contrast, so use it only for large display text. Never use it for body copy.

## Mock

[The approved mock](../mocks/fine-print-loader.html) shows the full loader. Its data is made up, and this spec overrides it if they disagree.
