# Interaction refinements — November 8, 2026

The owner’s follow-up supersedes the earlier dialog-only Save decision and the rolling headline treatment. This update addresses the reported focus, bookmarks, walkthrough and expanded-date behavior without changing the Search pipeline or source-fact assembly.

## Reproduction and changes

- The previous input stopped its typewriter but left the partial placeholder visible. The browser regression failed before the change. It now omits the placeholder on focus or whenever actual text exists, restoring the example only to an empty, unfocused home input.
- Save was disabled once selected and photos had no bookmark action. The new regression failed on the missing photo control. Ticket and 44px photo buttons now toggle the same guest/account saved state, serialize pending writes per Concert, and expose confirmation or error feedback without moving the cards. Account removal retains rollback.
- A further account regression deliberately failed a DELETE while saving another Concert. It reproduced loss of that second save because rollback restored the entire old list. Rollback now reinserts only the failed removal, retaining other current saves and the existing owner guard.
- The third walkthrough panel itself was a reset target, so its white background faded. The background now wraps a separate animated content container. The sequence awaits the complete 500 ms name narrowing, then holds 200 ms before picks enter. The regression checks the first visible pick against the finished candidate opacity, and all three opaque surfaces during reset.
- Expanding Calvin Harris’s eight additional dates moved the old dialog by 123 px and enlarged its photo. The new test failed on that geometry. Opening now locks a bounded frame, while the details pane scrolls independently. Grid rows, mobile photo sizing and Close remain outside that scroll. Existing photo travel and reverse close use the same frame.

## Hero library research and adaptation

Reviewed [PQINA Flip](https://github.com/pqina/flip), [react-split-flap](https://github.com/chiakich/react-split-flap) and the copyable [Solari React implementation](https://github.com/codemanshan/splitflap). Selected MIT-licensed **react-split-flap 0.2.1**, pinned in the lockfile: its `LongFlap` supports formatted React content and supplies the two-stage clipped 3D motion directly. No flap mechanics were invented locally.

The application supplies its existing Anton type, Moss paper/ink and coral places. Scoped overrides remove the library’s default font, hardware tiles, hinge, gradients, borders and shadows; only the folding type remains, with opaque faces preventing ghost text through the fold. The engine loads in a separate client chunk with a static server-rendered first phrase. Reduced motion uses static text and does not mount the engine. Frame inspection confirmed the correct font, page background, hidden decorative pseudo-element, clipped half panels, complete next phrase after settling and no page errors at 1280 and 390.

## Recorded example

One real public Search, **“Calvin Harris in SoCal next May”**, was captured through `run_search` under the existing shared spend guard on November 8. It considered 40 Concerts with 19 candidate names and returned Calvin Harris, Harry Styles/Kylie Minogue and French 79. Calvin’s source record includes eight more dates. The interpretation, names, Concerts, photos, reasons and grouped dates are retained in `frontend/lib/how-recording.json`; absent values remain absent. No Spotify account data was involved. Capture telemetry: 3.672 seconds and $0.000614598. Replaying the demo calls no provider or model.

The older Khruangbin public recording is now a browser-test fixture, keeping its Ticket motion assertions independent of the changing home demonstration.

## Validation

Before the fixes, the focus/bookmark checks and demo-sequencing/Ticket-geometry checks failed on the existing production build. After implementation, all 16 focused desktop/phone checks passed. The independent account rollback regression also reproduced before its repair. The first broad run passed 88 journeys and caught a reduced-motion server/client markup mismatch in the hero in two cases. The hero now renders identical static content through hydration before conditionally loading animation; focused real-font reduced-motion checks at both widths report no page errors and no mounted flap engine. A clean full 90-journey run and final `make check` follow this correction; **all 90 final browser journeys passed without retries (8.8 minutes)**. Final `make check` passed lint/types, 253 API contracts and 61 frontend data tests, and the normal production build passed. The same source was used for the final local preview and performance sample.

Physical-phone frame rate, screen-reader acceptance and real hosted Google/Spotify consent remain separate from automated Chromium and local Supabase verification. No merge, production promotion or hosting setting change is included.


## Performance sample

The final prerendered home HTML references 340,790 B compressed JavaScript, 53,296 B fonts and 13,086 B CSS (407,172 B total, deduplicated script/link paths with Python gzip). That is 3,556 B above the preceding motion build (403,616 B). The split-flap engine is a separate 4,735 B compressed chunk. The comparison excludes variable photos, Turnstile and later account SDK chunks as in prior measurements; it is not a production network trace.

Two nine-second local Chromium samples at 1280 and 390 covered two hero flips plus the photo-strip changes. They recorded 541/540 frame intervals respectively, p95 16.7 ms, max 16.8 ms, no >50 ms intervals, no long tasks and no page errors. Raw artifact: `.agent-context/refinements/frame-sample.json`. This is bounded local evidence, not a physical-phone frame-rate guarantee. No Search provider/model request is added by the hero or demo replay.
