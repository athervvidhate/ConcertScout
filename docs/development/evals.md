# Capture, judge, replay

The 20 drafts in `api/evals/searches.yaml` are not human judgments. Capture evidence first, then let the owner label it. An automated run must never supply relevance labels or claim that unjudged Recommendations meet the quality targets.

## Capture real data

Run from `api/` with the normal private `.env` and local Redis running:

```sh
uv run python -m evals.capture                               # one unjudged Search
uv run python -m evals.capture --limit 20 --max-cost 0.05     # up to20 serial captures
uv run python -m evals.capture four-tet-london --limit 1      # explicit case
```

These make real source and model calls. The runner checks the normal shared daily/monthly recorded-spend counters before each capture and records measured model usage even when a later pipeline step fails. It stops before starting another Search when the batch's measured cost reaches the threshold, or when cost is incomplete. An in-flight Search can exceed the threshold; this is not a billing reservation. Existing provider/account spend limits still apply.

Each capture has a fresh isolated in-memory cache to measure a cold source path; it does not reuse the app's public cache. Provider pacing is active inside each serialized capture. Avoid running several capture processes alongside one another: their isolated source gates are not a distributed quota across jobs. The shared Redis in this workflow is the spend ledger. Production app workers continue to use shared Redis for their own source gates and cache.

A unique Snapshot stores actual source responses, model answers/usage, capture date, original latency and whether the optional Last.fm fallback was enabled. Keys are removed from request identities and echoed response/answer text. Live responses are left unchanged. Snapshots and batch reports are private files in gitignored `evals/snapshots/`; they must not be attached to a public PR. Captures never overwrite earlier evidence. Old draft-format Snapshots without the source-configuration field must be recaptured.

The private `batch-*.json` report lists case/Snapshot IDs, observed latency, Recommendations, errors and actual cost. A failed provider is recorded as an error, not retried silently to manufacture a successful batch. The CLI exits unsuccessfully for an error, incomplete cost or a threshold-shortened batch; completed snapshots remain available.

## Human judging without another paid run

Use the case and Snapshot IDs from that report:

```sh
uv run python -m evals.judge four-tet-london --snapshot <snapshot-id>
```

This replays locally with no provider/model requests and no keys required. The Search text must match and every request must be present. A changed prompt or shortlist can make an old Snapshot unsuitable; the tool refuses to label it silently.

Read the Search and Poster, then label at most20 Artists with `m`/`must`, `g`/`good`, `b`/`bad` or Enter/`neutral`. Invalid input asks again. Add missed must-find Artists when prompted, then notes. Only a completed review writes labels and `judged: true` to the YAML. An all-neutral review is valid; an interrupted review writes nothing. `uv run python -m evals.judge <id>` still captures and judges in one session, with a real paid capture.

To rate in the browser instead, run `uv run python -m evals.rate`. It opens http://127.0.0.1:8765 with every Search from the newest batch report (`--batch <name>` picks another), replays each offline with no keys or cost, and shows the Poster first with its reasons, then the shortlist, each with a Spotify search link. Keys `m`, `g`, `b` and `n` label the highlighted Artist and move down. Save writes the same YAML fields as `evals.judge`, and a rated Search can be opened again and changed.

The tool does not infer why a person likes an Artist or label a missing Artist for them. Snapshot responses alone cannot prove Recommendation quality.

## Scorecard

```sh
uv run python -m evals.scorecard --batch <batch> [--runs 5] [case ...]   # ranker live, about $0.10 for 20 Searches
uv run python -m evals.scorecard --batch <batch> --live all              # the interpreter too, as a visitor sees it
uv run python -m evals.scorecard --batch <batch> --live none [--pool]    # shortlist only, no ranker calls
```

This repeats each captured Search and scores every Poster without labels: overlap between runs, silver recall against Deezer and Last.fm, and the share a stronger model grades a fair fit. The measures and their limits are in [the evals spec](../specs/06-evals.md#measures-without-labels). A line per Search lists the Artists that came and went between runs, with their grade, so a flaky pick is easy to see.

With the default `--live ranker`, every run sees the same shortlist, so any change is the ranker's. `--live all` also reads the Search afresh. A run whose new reading asks for a source call the Snapshot lacks has no fair Poster and counts as failed; that count is itself a measure of how steady the interpreter is.

`--live none` is for matching changes. It calls no ranker, scores only the shortlist and pays only to grade Artists not graded before. `--pool` grades everyone playing as well, to show how many strong fits matching could have found. A large pool costs several cents the first time.

Deezer answers and grades are cached in `evals/snapshots/silver-cache.json` and `grade-cache.json`, so a second run only pays for the ranker. Deezer permits only private, non-commercial use, so its answers stay in that private folder and never reach the app. Every paid call counts toward the shared daily and monthly spend caps, and the scorecard stops before a Search once a cap is reached.

## Compare two runs

```sh
uv run python -m evals.compare --before <batch> [<batch>...] --after <batch>
```

This reads the Snapshots themselves and makes no calls, so it works across code changes that stop an old Snapshot replaying. For each Search it lists the Artists the model would put on the Poster, who was lost and who is new, with their scores. A Poster count hides this: stacking dates shrinks it without losing an Artist.

Two runs of the same input differ too, so a change only means something if it is bigger than that noise. Nothing here says which run is better. That still takes human labels.

## Replay the evidence

```sh
uv run python -m evals.run
uv run python -m evals.run --live ranker  # new ranker spend after a ranker change
uv run python -m evals.run --live all     # new spend for every model request, after an interpreter change
```

The ordinary run reads completed human labels and replays recorded HTTP/model answers through the real pipeline. It reports all measures in the spec, including captured cold latency and recorded token cost; replay wall time is not a production-speed measurement. Optional source configuration is restored from the Snapshot. Replay-only pacing is scoped and restored before any later capture.

Missing requests or a pipeline error produce a failed case rather than a silent quality score. No must labels means recall is not measurable; it does not mean100% recall. With no human reviews the runner says that none are judged. The paid `--live` modes use fresh model answers against the recorded sources; they are not offline runs. `--live ranker` keeps the recorded reading of the Search, so the shortlist cannot change under it.

Run the app/contracts with `make check`. Transport tests use generic echo data and typed app-owned seams, not invented vendor response schemas.
