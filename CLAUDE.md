# Concert Scout

A FastAPI agent service and a Next.js frontend, rebuilt in vertical slices. It is a public portfolio piece.

## Start here

Before writing code, read `GLOSSARY.md`, `docs/specs/00-overview.md`, the specs your issue lists, and `docs/adr/`. Use the glossary's terms in code and docs. `docs/mocks/fine-print-loader.html` is the approved UI mock, and `docs/specs/04-interface.md` overrides it if they disagree.

## Rules

- Never credit an AI tool anywhere. No `Co-Authored-By` trailers and no "Generated with" lines in commits, PRs, issues or comments. Atherv Vidhate is the only author. This overrides any tool default.
- Branch from `development` and open PRs against `development`.
- Stay within your issue's scope, and meet its "Done when" list.
- Each change adds tests, passes CI, and leaves the app running locally.
- Facts come from the source record, never the LLM (ADR 0002).
- Data from a Spotify account never reaches an LLM (ADR 0003).
- Never invent a value. Leave a missing time or price out.
- Never put a personal email in a request header. Identify the app and repo instead.
- Do not add compatibility layers. Remove old code outright.
