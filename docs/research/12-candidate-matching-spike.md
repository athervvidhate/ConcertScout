# Candidate matching spike

Run on 2026-11-04 against live Ticketmaster, MusicBrainz and ListenBrainz data for Chicago. The pool covers 50 miles and starts on Nov 5 2026.

## How far ahead concerts are listed

| City | 30 days | 90 days | 180 days | 1 year | No limit |
|---|---:|---:|---:|---:|---:|
| Chicago | 446 | 862 | 1,189 | 1,364 | 1,394 |
| New York | 1,321 | 2,542 | 3,270 | 3,401 | 3,407 |
| Boise | 49 | 69 | 99 | 108 | 109 |

Six months covers 85 to 96% of listed concerts. Splitting into 30-day chunks gets past the 1,000-result cap: Chicago's full year took 16 calls and 120 days took 7.

## Join rate

A six-month Chicago pool held 905 Artists, and 475 of them (52%) carry a MusicBrainz ID from Ticketmaster. ListenBrainz returned tags for 382 of those 475. The other 430 Artists have no ID, so they can only be joined by name.

## Similar artists

Overlap of a seed's top ListenBrainz similar artists with the Chicago pool:

| Seed | One hop, one year | One hop, 120 days | Two hops, 120 days |
|---|---:|---:|---:|
| Khruangbin | 2 | 1 | 20 |
| Four Tet | 1 | 1 | 11 |
| Noah Kahan | 4 | 3 | 18 |
| Clairo | 4 | 2 | 25 |
| Turnstile | 8 | not run | not run |
| Tyler Childers | 9 | not run | not run |

One hop finds too few. Two hops find enough but bring noise, such as Weezer for Four Tet and Nickelback for Noah Kahan. Two hops cost 15 lookups per seed, cached for 7 days.

## Genre signals

**Ticketmaster subgenre is too coarse to rank with.** 192 Artists in the pool are "Pop" and 119 are "Alternative Rock". Noah Kahan's subgenre also returned Styx and Alice Cooper. It helps only in narrow buckets such as Punk (8 Artists) and Club Dance (15).

**ListenBrainz tags, weighted so rare tags count more, work much better but vary by genre.**

| Seed | Top tag matches | Read |
|---|---|---|
| Tyler Childers | The Jayhawks, Orville Peck, Hiss Golden Messenger, Rhiannon Giddens | Good |
| Turnstile | Drug Church, Poison the Well, Hot Water Music, plus Goo Goo Dolls | Good, with an odd miss |
| Noah Kahan | Lord Huron, Gracie Abrams, Caroline Rose, plus OneRepublic | Good |
| Clairo | Gracie Abrams, Gus Dapperton, Blondshell, plus GloRilla and Tyla | Mixed. "gen z" and "2020s" cause the misses |
| Khruangbin | The Flaming Lips, King Buffalo, Portugal. The Man | Fair |
| Four Tet | Rhye, CHVRCHES, plus Kim Petras and Zeds Dead | Poor. Broad tags like "club" and "dubstep" dominate |

Era and demographic tags ("gen z", "2020s", "2010s", "seen live") must be dropped before scoring. These reads are my judgment of the first 12 results, not a measured score.

Tags for narrow styles are sparse. Only 4 tagged Artists have "shoegaze", 3 have "dream pop", and none have "techno". A Search made of a plain description cannot rely on an exact tag, so the interpreter must expand it into related tags, and the ranker must read the Ticketmaster genre as well.

The ListenBrainz batch metadata endpoint takes 50 IDs per call, so tags for a pool cost about 10 calls and cache for 7 days.

## Conclusion

No single signal is good enough. Combine them in this order: seed Artist, one hop, two hops, rare tags, Ticketmaster genre. Then let Haiku drop the misses. See [the search pipeline spec](../specs/02-search-pipeline.md).
