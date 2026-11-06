# Ticket input contracts — November 6, 2026

Issue #24's keyboard and browser gesture behavior now has production end-to-end coverage. Physical-phone acceptance remains pending.

- All22 browser checks passed at1280px desktop and390px mobile (touch/mobile context enabled), with no retries. Existing production webpack build was reused because product code was unchanged.
- Keyboard journey uses Tab to reach controls, ArrowRight to Save the first source Concert, ArrowLeft to Skip the next, Enter to open Saved Concerts and Space to remove a Concert. Saves survive a reload and removal survives another reload. Two Concerts share an Artist name, so the journey also guards source-ID identity.
- Gesture journey sends native mouse input on desktop and Chromium native touch input on mobile. A slow short drag returns without a decision. A right drag Saves and advances; a left drag Skips; Saved Concerts persist across navigation/reload and exclude the skipped source Concert.
- Initial drag runs failed only at reload: the test reloaded26ms after clicking the Next.js link, cancelling unfinished navigation and returning to Home. Waiting for the Saved URL resolved both viewport failures; no app fix was needed. The narrowed mouse/touch runs passed, followed by the full22-check suite.
- Frontend lint and typecheck passed. Backend133 contracts and19 frontend data tests passed on the unchanged product code in the preceding continuity change. The new CI runs all22 browser checks.

These journeys use the existing real API/pipeline, isolated Redis and typed domain fixtures. No external provider response schema, Motion callback or DOM-dispatched pointer event is faked. They run with reduced motion to isolate interaction from loader timing. The separate normal-motion journeys continue to cover the Search presentation path.

A browser's emulated touch is not a physical phone. Keep the real-phone Done-when item unticked until an owner test is recorded.
