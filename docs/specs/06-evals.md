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

`uv run python -m evals.run` prints every measure. It replays each Snapshot, which holds every outbound call and model answer, so it needs no keys or network and costs nothing. A prompt, weight or shortlist change makes new model requests, so use `--live-model`, which calls the real model and costs money. Time to `poster` always comes from the cold capture, because a replay makes no real calls.

Run the evals in CI only by hand or nightly, because they cost money. Fixture tests for `matching.py` run on every push.

## Tuning

Use the evals to set the weights in [02-search-pipeline](02-search-pipeline.md), the top-40 size and the tag blocklist. Change one at a time. Record what moved each score.
