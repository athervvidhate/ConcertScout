# Concert source coverage audit

This developer-only experiment runs outside the production Search. It makes no model calls and does not change the source pool, ranker, browser or deployment. The first evidence is in [the November 7 audit](../validation/2026-11-07-coverage-audit.md).

## Run and replay

From `api`, with installed locked dependencies:

```sh
uv run python -m evals.coverage capture \
  --references evals/coverage-references.json \
  --output evals/snapshots/coverage/capture.json \
  --max-requests 50

uv run python -m evals.coverage replay evals/snapshots/coverage/capture.json

# Optional JamBase audit, with a private key file or JBD_API_KEY in the environment.
uv run python -m evals.coverage capture --providers jambase \
  --jambase-key-file /path/to/private/key-file --max-requests 10 \
  --output evals/snapshots/coverage/jambase.json

uv run python -m evals.coverage compare \
  evals/snapshots/coverage/capture.json evals/snapshots/coverage/jambase.json \
  --provider jambase
```

Capture reads `TM_KEY`, `JBD_API_KEY` and optionally `REDIS_URL` from the environment/ignored `.env`; only keys for the selected providers are needed. Use `--env-file /absolute/path/to/.env` for an existing local configuration. No model keys are required. Default providers remain Ticketmaster and Ticket Fairy; JamBase is explicit opt-in. Capture refuses to overwrite evidence; choose a new output filename for another run. It uses the existing Ticketmaster shared limiter and falls back to local pacing if Redis is unavailable. Requests are sequential, have a timeout, make no automatic retries and stop at the configured request budget (at most 100). The default 50 requests is a ceiling, not a target.

JamBase first checks `/v3/quota` and stops if included quota cannot be verified or is exhausted. The quota check counts toward the audit's HTTP request ceiling and is recorded as a control request; the provider does not charge it against included catalog calls. The captured quota is the verified **preflight** value; a local counter conservatively decrements for successful catalog requests. No overage or paid-plan change is authorized by this command. Check account usage separately afterward when confirming billing. The included-quota guard is not an account-wide lock against unrelated callers spending quota concurrently.

Capture saves source responses, normalized Concert records, per-lookup completeness/errors, request counts, elapsed times, the reference manifest and capture time. File permissions are owner-only; default captures live in the existing gitignored snapshots directory. Request URLs/headers and credentials are not saved; known credential values and URL encodings are redacted from response bodies. Do not commit full vendor pages or captures. The tiny test fixture retains selected unaltered fields from the live responses and records that it is not a full page.

Replay reads only the saved typed records, recalculates identity comparisons and summaries, and needs no network or keys. `compare` measures confirmed additions against a Ticketmaster baseline, counts overlap once, separates newly resolved references from proven additions, and rejects differing frozen reference sets/windows. A new adapter/parser requires a fresh normalization/capture; replay does not silently re-extract facts from raw payloads with a changed parser. Timings in the report remain the original capture timings. The tool does not run the app's matching, shortlist or ranker: provider absence and final Poster recall are different measures.

## References and interpretation

`evals/coverage-references.json` is a hand-reviewed reference set derived from venue calendars. Each entry has a source-qualified reference ID, canonical source URL, published name aliases, local date, venue/city aliases and Artist/title search keywords. SHA-256 hashes identify the local HTML evidence used to construct the original manifest; those private captures are not required to replay a saved audit. When changing dates or venues, read and verify the new source records and update the manifest/evidence rather than assuming the old list remains current. This command deliberately does not install a recurring venue scraper.

The unit is a **venue date**. Multiple sets on one night remain a single coverage reference; recovering a date does not establish all set times or ticket availability. Missing time/price remains missing. Never infer that a tribute or afterparty title proves the named Artist performs. The manifest records excluded programs and reasons so selection is inspectable.

Ticketmaster probes every distinct venue and reference keyword in the fixed country/state/date window, without a Music filter so classification cannot hide a candidate. Each lookup pages to completion within its documented 1,000-row ceiling and the audit's request budget. Ticket Fairy currently supports a single documented California/date-window probe with pagination, no keyword restriction; another geography is marked unsupported rather than silently searched as California. The audit does not imply either API has an exhaustive catalog.

JamBase queries `/v3/events` once per reference venue/country/window, paging at 100 records per page, and compares the returned venue/city/Lineup rather than trusting a venue-name keyword match. The upper date bound includes the next day to avoid excluding late performances on the reference's last local date; exact reference dates are still required for a coverage win. The parser preserves JamBase IDs and published Lineups, keeps unknown time/price absent, and retains the JamBase source URL. It does not infer a direct ticket checkout from a generic venue-homepage offer.

The conservative comparison uses exact normalized published aliases for Artist/title, venue, city and date:

- **present:** a record agrees on that identity and date. An external checkout link still counts as present in Ticketmaster discovery.
- **missing:** every required lookup completed, and no matching venue date was found. This means missing from these bounded lookups, not every system the vendor operates.
- **unresolved:** an error, missing query, truncated/inconsistent page, cancellation/postponement, unknown date, unrecognized same-venue/date title, or possible reschedule prevents a confident answer.
- **out_of_scope:** the reference is outside the requested dates.

Provider IDs returned by several keywords count once. Multiple distinct IDs on a date are flagged for review, not automatically merged: they may represent duplicates or separate sets. Other dates for an identity are preserved as evidence rather than moved to the reference date. Human review is necessary for aliases, calendar mistakes, multi-stage venues and status conflicts. Add confirmed aliases to the reference manifest, not fuzzy guesses to the classifier.

## Next source decision

Measure additional **verified canonical dates**, requests, freshness, conflicts and maintenance effort. For production, also test that useful added Concerts survive matching/shortlisting and reach a Poster. Keep collection outside the Search latency budget; a measured offline comparison is not a measured Search speedup.

The owner's privately supplied key enabled the follow-up JamBase audit recorded in the evidence report: seven verified additions in this sample, with no overage. This is an audit parser, not a production source adapter. Public JamBase venue pages alone cannot establish Developer-plan entitlement, payload fields, quotas or API recall. See Tickets feed access and recurring venue crawling remain separate access questions. Do not add another source to the production path merely because its endpoint returns HTTP 200.
