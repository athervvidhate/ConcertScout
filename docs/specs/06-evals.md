# Evals

"Good" means what a real person would call good, so a human judges it. We judge 20 Searches by hand and turn those judgments into Pydantic Evals cases.

## Why snapshots

Ticketmaster data changes every day, so a judged Search would go stale. Each case stores a snapshot of its Concert pool. Snapshots hold third-party data, so they stay out of git in `evals/snapshots/`.

## Case format

`evals/searches.yaml`:

```yaml
- id: khruangbin-chicago
  text: Something like Khruangbin in Chicago, next two weekends
  snapshot: khruangbin-chicago-2026-11-20
  must: [Hermanos Gutiérrez]
  good: [Altın Gün, Men I Trust]
  bad: [Weezer, Nickelback]
  notes: Patient, groove-led instrumental music
  judged: true
```

`judged: true` records a completed human review, including a valid all-neutral review. A captured draft alone is not judged. `must` Artists should appear, `good` ones may, and `bad` ones must not. Anything unlisted counts as neutral.

## Search set

The 20 Searches should cover the pipeline's weak spots:

- Seeds where tags worked in the spike (Tyler Childers, Turnstile).
- Seeds where tags failed (Four Tet, Khruangbin).
- Plain descriptions with no Artist ("dreamy guitar music").
- Styles with sparse tags (shoegaze, techno).
- A large city, a small city (Boise), and no place at all.
- No dates, a weekend, and a far-off month.
- A Search with no good answer, which should give a short Poster.

## Judging

`uv run python -m evals.judge` snapshots a Search, runs the pipeline, and lists the shortlist. The judge marks each Artist `must`, `good`, `bad` or neutral, and the tool writes the YAML. It takes a few minutes per Search. Marking a sample of 20 Artists per Search is enough.

For advance capture, `uv run python -m evals.capture --limit 20` records the drafts serially without writing labels. Its measured cost threshold stops before another Search, not during one; the shared recorded-spend guard also applies. `uv run python -m evals.judge <id> --snapshot <snapshot-id>` then judges one capture offline, without keys or another paid request. See [the eval workflow](../development/evals.md).

## Measures

| Measure | Target |
|---|---|
| `bad` Artists on a Poster | 0 |
| `must` Artists found | At least 90% |
| Share of Poster judged `good` or `must` | At least 60% |
| Invented facts or unknown IDs | 0 |
| Time to `poster` event, p95 | Under 15s |
| Cost per Search | Measured and recorded |

`uv run python -m evals.run` prints every measure. It replays each Snapshot, which holds every outbound call and model answer, so it needs no keys or network and costs nothing. A ranker change makes new ranker requests, so use `--live ranker`, which keeps the recorded reading of the Search and calls the real ranker. An interpreter change needs `--live all`. Both cost money. Time to `poster` always comes from the cold capture, because a replay makes no real calls.

Run the evals in CI only by hand or nightly, because they cost money. Fixture tests for `matching.py` run on every push.

## Measures without labels

Human labels are the final word, but there are only as many as the owner has time to give. Three checks run without them, so a change can be judged before any label exists. `uv run python -m evals.scorecard` reports all three per Search. See [the eval workflow](../development/evals.md#scorecard).

| Measure | What it asks | Target |
|---|---|---|
| Overlap | Do repeated runs of one Search give the same Poster? Mean pairwise Jaccard of Artists. | At least 80%, lowest Search at least 60% |
| Silver recall | For a Search that names an Artist, how many Artists that Deezer or Last.fm call similar, and who are playing, reach the Poster? | Rises, never falls |
| Graded precision | What share of the Poster does a stronger model grade a fair fit or better? | At least 60% |

Each has a known weakness, so no one of them decides alone:

- A ranker that always returns the same bad Poster scores 100% overlap.
- Deezer and Last.fm learn from listening, like ListenBrainz, so they share its popularity bias and miss small acts. Agreement with them is consistency, not quality. Neither feeds the candidates, which keeps the check from rewarding the pipeline for repeating its own data. If Last.fm ever does, it leaves the silver set.
- The grader is a model. It never sees why an Artist was shortlisted, but it shares blind spots with the ranker and grades Artists it does not know as a stretch. It counts only while it agrees with the owner's labels.

The scorecard also grades the shortlist, which shows whether a weak Poster is the ranker's fault or the matching's. With `--pool` it grades everyone playing, which shows when a pool holds no good answer at all. Ticketmaster lists little underground techno in Detroit, for example, so no change to matching can find it.

## Tuning

Use the evals to set the weights in [02-search-pipeline](02-search-pipeline.md), the top-40 size and the tag blocklist. Change one at a time. Record what moved each score.
