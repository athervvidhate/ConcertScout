# Portfolio finish — November 6, 2026

Issue #32 adds a README explaining the Search pipeline, source-fact boundary, privacy, evaluation commands and unresolved acceptance work. `/privacy` describes the current data flows and retention, including operational log limits rather than promising that hosts keep no logs. `/credits` links every source, data licenses, the official Spotify logo and portfolio. The common footer opens policy pages without replacing an active Poster.

Validation:

- `make check`: lint/types, 116 Python contracts and 19 pure frontend data tests passed.
- Production webpack build passed; all 18 browser checks passed at 1280px and 390px.
- The Search-to-Save journey now opens Privacy in a new tab, confirms the active Ticket survives, follows the credits link, checks both pages for horizontal overflow, then continues Save/navigation/reload. Its final two viewport runs passed.
- Inspected full-page Privacy and credits screenshots from the production browser journey at both widths; no clipping or overlap observed. Screenshots are local, ignored `frontend/test-results/.../privacy.png` and `credits.png` artifacts. T3 snapshots timed out twice; Yab also verified the local pages at 1024px.
- The portfolio link was verified at https://atherv.com. Local frontend on 3000 and API health on 8000 remain available.

CI is reported by the PR. Public hosting (#31), live Spotify consent (#29), human relevance labels (#22) and physical-device drag acceptance (#24) are separate pending steps. This change does not claim them complete.
