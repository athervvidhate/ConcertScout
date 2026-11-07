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
