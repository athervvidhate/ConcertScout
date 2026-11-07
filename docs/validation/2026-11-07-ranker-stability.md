# Why Poster sizes moved between eval runs — November 7, 2026

Posters went from 114 entries to 96 after the Search usability work, and three Searches dropped hard. Most of that drop was not lost Artists. The real finding is that the ranker gives different answers to identical input. No human labels exist yet, so nothing here says which picks are better.

## What changed between runs

`evals.compare` counts distinct Artists scoring 50 or more, using all 20 captures from each run.

| Run | Poster entries | Distinct Artists | Overlap with previous run |
|---|---:|---:|---:|
| November 6, before stacking | 114 | 95 | |
| November 6, after usability work | 96 | 94 | 49% |
| November 7, venue time and geocoder fixes | 98 | 95 | 68% |

Ticketmaster pools held steady, within a few percent per Search, so the source data did not cause this. Stacking accounts for the entry count. `no-place-khruangbin` went from 8 entries to 3 with 3 Artists both times, because one Artist's dates now share a row.

The run-to-run swing comes from chance. `ambient-seattle` went from 5 Artists to 1, then back to 6, with no prompt change between the last two runs. `four-tet-boise` went 2, 0, 1.

## Repeat test

Five Searches with a shrinking Poster each ran through the ranker five times per variant, on the captured November 6 input. Overlap is the mean pairwise overlap of the Artists picked. The test cost about five cents.

| Search | Variant | Artists per run | Overlap |
|---|---|---|---:|
| ambient-seattle | current | 7, 7, 7, 2, 7 | 57% |
| | old prompt | 7, 7, 7, 7, 7 | 100% |
| | shortlist of 60 | 8, 1, 8, 1, 7 | 31% |
| boise-shoegaze | current | 4, 0, 2, 3, 3 | 28% |
| | old prompt | 3, 2, 2, 2, 3 | 62% |
| | shortlist of 60 | 4, 2, 2, 2, 4 | 39% |
| khruangbin-chicago | current | 4, 3, 5, 6, 7 | 51% |
| | old prompt | 7, 7, 5, 8, 6 | 68% |
| | shortlist of 60 | 6, 6, 0, 7, 8 | 44% |
| four-tet-boise | current | 0, 1, 1, 1, 0 | 40% |
| | old prompt | 2, 1, 2 (two runs failed) | 67% |
| | shortlist of 60 | 0, 0, 1, 1, 0 | 40% |
| shoegaze-portland | current | 0, 0, 0, 0, 0 | 100% |
| | old prompt | 0, 1, 0, 0, 0 | 60% |
| | shortlist of 60 | 0, 0, 1, 0, 0 | 60% |

"Old prompt" is the ranker's instructions from before the usability work. "Shortlist of 60" restores the old size with the current instructions.

## Findings

- The ranker is the main source of change. Identical input can produce a full Poster or almost nothing, and a visitor who repeats a Search can see a different one.
- The prompt rewrite made this worse. The old instructions gave a higher overlap on four of the five Searches. The fifth is shoegaze-portland, where the current prompt scores 100% only because it picked nobody in any run.
- Cutting the shortlist from 60 to 40 did not cause the drops. Sixty rows was no steadier, and it produced more near-empty runs.
- This is five runs of five Searches, so it shows a direction and does not measure every Search.

## Latency

The November 7 run took a median of 12.8 seconds and a p95 of 19.9 seconds to reach a Poster, against 12.6 and 16.6 before. It misses the 15-second target by more than the last run did. With 20 samples, p95 is one slow Search.

## Next

Stability can be fixed without labels, because it asks whether the same input gets the same answer, not whether the answer is good. Try the old selection wording with the new reason wording, and keep whichever is steadiest on this repeat test. Choosing between sets of Artists still waits on the owner's labels.

# Measuring the ranker without labels — November 7, 2026, later

The repeat test above became `evals.scorecard`, which scores every repeated Poster three ways without labels: overlap, silver recall against Deezer and Last.fm, and a stronger model's grades. [Research note 13](../research/13-similarity-and-ranking-evaluation.md) covers the sources and methods. All runs below use batch `batch-2026-11-07-073158-af052017`, 20 Searches, 5 runs each, with sources replayed and the ranker live.

## Two sources of change

With the interpreter live too, as a visitor sees it, mean overlap was 77% and 29 of 100 runs could not replay at all: the interpreter read the Search differently and asked for source calls the Snapshot never recorded. Six Searches got more than one shortlist. Holding the recorded reading fixed and calling only the ranker live gave 74% mean overlap, lowest 30%. Both the interpreter and the ranker move the Poster. This change fixes only the ranker.

## The ranker grades instead of choosing

Asked to choose up to 8 Concerts, the ranker sometimes picked a full Poster and sometimes almost none for identical input. `ambient-seattle` gave 1, 6, 6, 8 and 1 Artists over five runs. The new ranker grades every row 0 to 3 against fixed levels, runs three votes with the rows in different fixed orders, and takes each row's median. Code includes level 2 and up, ordered by level, then match score.

| | Overlap | Lowest | Silver recall | Graded precision | Graded recall |
|---|---:|---:|---:|---:|---:|
| Choose up to 8, one run | 72% | 30% | 15% | 60% | 60% |
| Grade every row, 3 votes | 82% | 40% | 15% | 64% | 65% |

| Search | Overlap before | Overlap after | Graded precision before | Graded precision after |
|---|---:|---:|---:|---:|
| tyler-childers-chicago | 53% | 66% | 84% | 88% |
| turnstile-new-york | 90% | 93% | 44% | 42% |
| four-tet-london | 57% | 80% | 88% | 88% |
| khruangbin-chicago | 54% | 70% | 33% | 56% |
| dreamy-guitar-seattle | 100% | 79% | 83% | 79% |
| shoegaze-portland | 100% | 100% | - | - |
| techno-detroit | 38% | 60% | 0% | 0% |
| boise-country | 63% | 83% | 81% | 66% |
| no-place-turnstile | 90% | 100% | 0% | 0% |
| new-york-jazz | 87% | 92% | 100% | 100% |
| chicago-far-month | 100% | 100% | - | - |
| boise-shoegaze | 36% | 40% | 0% | 0% |
| ambient-seattle | 30% | 90% | 75% | 82% |
| punk-los-angeles | 30% | 77% | 63% | 45% |
| folk-austin | 71% | 91% | 88% | 88% |
| four-tet-boise | 100% | 100% | 0% | - |
| instrumental-san-francisco | 58% | 76% | 94% | 100% |
| metal-denver | 91% | 56% | 88% | 92% |
| no-place-khruangbin | 100% | 87% | 100% | 100% |
| sparse-answer | 100% | 100% | - | - |

A dash means nothing to measure: no Poster Artists beyond seeds, or none graded. Grading cost $0.15 once and is cached. The ranker part of each run cost about $0.09 before and three times that after, still under a tenth of a cent per Search. Latency is measured in the next section.

Three Searches got less steady: `metal-denver`, `dreamy-guitar-seattle` and `no-place-khruangbin`. All three still hold their quality. Five runs per Search is a small sample, so single rows move by chance.

## Speed: thinking off

Three votes with thinking on made the rank step the slowest in a cold Search: 8.2 seconds median, 10.8 at p95, in 20 captures (`batch-2026-11-07-183818-f8570535`). The scorecard compared three settings on that batch, 3 runs each, with sources replayed:

| Ranker | Overlap | Lowest | Graded precision | Graded recall | Ranker call median | p95 | Cost |
|---|---:|---:|---:|---:|---:|---:|---:|
| Thinking on, 3 votes | 89% | 66% | 61% | 56% | 6.1s | 10.6s | $0.186 |
| Thinking off, 3 votes | 87% | 60% | 58% | 56% | 3.6s | 5.5s | $0.124 |
| Thinking off, 1 vote | 78% | 33% | 62% | 52% | 2.9s | 4.6s | $0.057 |

Thinking off with 3 votes keeps the quality within the noise of 3 runs and nearly halves the time. One vote saves another 0.7 seconds but loses the steadiness this change exists for. The ranker now runs with thinking off and 3 votes.

A cold capture of all 28 Searches with that setting (`batch-2026-11-07-185048-ea95fcc0`, $0.059) gave:

| | Search median | Search p95 | Rank median | Rank p95 |
|---|---:|---:|---:|---:|
| Thinking on (20 Searches) | 15.7s | 21.9s | 8.2s | 10.8s |
| Thinking off (28 Searches) | 12.6s | 19.0s | 3.8s | 4.9s |

The Search p95 still misses 15 seconds. The slow Searches now lose their time in the Ticketmaster pool (up to 8.6 seconds for `pop-new-york`) and in matching (up to 6 seconds), not in the ranker.

## Most misses come before the ranker

The ranker can only pick from the 40 it is given, and the grader rates most shortlists poorly. Under a third of shortlisted Artists grade a fair fit or better. Across seven Searches that name an Artist, 36 silver Artists were playing and 10 reached the shortlist.

Tracing each miss showed why. Charles Wesley Godwin is a ListenBrainz neighbour of Tyler Childers but sits near the end of its list of 50, so he scores 0.22, under the 0.30 a narrow Ticketmaster genre earns. Scoring neighbours by their place in the list instead was tried and changed nothing measurable, because such Artists already sit near the end. That change was reverted.

Grading every Artist playing, with `--pool`, showed that `techno-detroit` and `boise-shoegaze` have no strong fit anywhere in their pools. Ticketmaster lists little underground techno or shoegaze in those cities, so no change to matching or ranking can find one. The remaining pool grades were stopped by the daily cap.

## Grader limits

The grader ranks Bonobo a 3 for ambient and Katseye a 0, as a person would. It rated Arc De Soleil, a band close to Khruangbin, a 1, because it does not know them and its instructions cap unknown Artists there. Silver recall covers that gap only for Searches that name an Artist. No grade here is checked against human labels yet, so graded precision is a model's opinion.

## Next

- Profile the pool and match steps, which now hold the Search p95 above 15 seconds.
- Grade the remaining pools, to tell missing candidates from missing Concerts for every Search.
- Hold the interpreter steady. It changes the shortlist for six Searches out of twenty.
- Label a sample, so the grader's agreement with the owner is known.

## Speed: tags while the pool arrives

The match step waited for the whole pool, then sent every ListenBrainz tag request at once. London needs 14 requests of 50 Artists. Replayed live, one request alone took 0.9 seconds and all 14 together took 4.0, returning in waves about a second apart, so ListenBrainz queues them. Tag batches now start as Ticketmaster pages arrive. Cold captures of the same 28 Searches (`batch-2026-11-07-192838-9bf3e016`, $0.060):

| | Search median | Search p95 | Match median | Match p95 | Match max |
|---|---:|---:|---:|---:|---:|
| Tags after the pool | 12.6s | 19.0s | 1.5s | 5.0s | 6.0s |
| Tags while the pool arrives | 11.4s | 16.8s | 0.5s | 1.4s | 1.8s |

Poster sizes held: 166 picks against 164. The pool step itself did not change, median 2.8 seconds, and is now the largest wait after the ranker.

## Speed: daily cache warming

`concert_scout.warm` runs the pool and tag lookups for 12 busy cities, once a day from Vercel's cron. Measured against local Redis, counting every command the way Upstash bills them, pipelined commands one by one:

| Run | Ticketmaster | ListenBrainz | Geoapify | Redis commands | Time |
|---|---:|---:|---:|---:|---:|
| Empty cache | 125 | 118 | 12 | 3,567 | about 70s |
| Everything cached | 0 | 0 | 0 | 215 | under 1s |

A daily run in production sits between the two: pools have expired after 6 hours and most tags are still cached. At the empty-cache worst case, 30 runs a month are 107,000 commands, a fifth of Upstash's free 500,000, and 125 calls a day are 2.5% of the Ticketmaster allowance. The warmed keys take 11.2 MB, 9.7 MB of it pools, out of the free 250 MB. No model is called.

Place names are written the way the interpreter writes them. "New York, NY" geocodes to a different 5-kilometre cell from "New York, New York, United States", and so to different cache keys. Every spelling the interpreter used in 28 captured Searches lands in the same cell as its city's entry.

The same 18 Searches in warmed cities, run live once on an empty cache and once after warming:

| | Search median | Search p95 | Pool median | Pool max | Match max |
|---|---:|---:|---:|---:|---:|
| Empty cache | 11.5s | 16.8s | 3.0s | 8.0s | 1.1s |
| After warming | 7.5s | 13.1s | 0.2s | 0.4s | 0.1s |

The pool now waits only for a seed Artist's own lookup. What remains for a Search that names an Artist is resolving that Artist and its neighbours (up to 8.5 seconds for `khruangbin-chicago` and `pop-new-york`) and the ranker. A city off the list, or a Search more than 6 hours after the run, is still cold.
