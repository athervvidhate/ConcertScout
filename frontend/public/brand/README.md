# Concert Scout identity

- `logo-light.svg`: pine wordmark and coral compass for light paper.
- `logo-dark.svg`: pale wordmark and coral compass for dark paper.
- `logo-pine.svg`: pale wordmark and lighter coral for the pine band.
- `mark-*.svg`: symbol only, for compact placements.
- `google-app-logo.png`: a square PNG for app-logo uploads such as Google Cloud.
- `logo-*.png`: transparent PNG exports of the final SVG lockups.
- `favicon-32.png`: small PNG rendition. Next.js serves the adaptive SVG, ICO and Apple icon from `app/`.

The SVGs contain outlined Anton lettering and no external resources. Backgrounds are transparent. Keep their aspect ratio and clear space; use the mark rather than shrinking the lettering below legibility. The header selects its rendition with the same light/dark token state as the page, before paint.

Rebuild paths with `scripts/brand/build-logo.py`. The SVGs are the production assets.
