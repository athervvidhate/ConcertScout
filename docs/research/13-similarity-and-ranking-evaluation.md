# Artist similarity data, ranking evaluation and ranker stability

Method: web search and page fetches on 2026-11-07, plus two live Deezer API calls from this machine. Builds on `11-artist-similarity-data.md` (2026-11-04) and `06-spotify-alternatives.md`; their findings are not repeated in full. Anything I could not confirm is marked UNVERIFIED. Search-snippet and third-party claims are labelled as such.

## Summary and ranked recommendation

The instability is most likely a threshold problem: the ranker emits a 0-100 score per candidate, many candidates sit near the 50 cut-off, and small score changes flip them in or out. (This is my reading of the 28-57% overlap figure, not something I tested.) Also, the newest Claude models do not let you set temperature, so "turn temperature to 0" is not available (see section 3).

Ranked by value for cost:

1. **Put a deterministic score in charge of inclusion; let the LLM only veto and write reasons.** Compute a score from similarity data you already have (hop count, LB/Last.fm similarity score, shared tags) and take the top picks from it. Ask the LLM for a bounded adjustment or a veto flag with a reason, never for the inclusion decision. Cost: no new data, one prompt change. This removes most variance by construction, and it is consistent with ADR 0002 (facts from the source record).
2. **Build a small evaluation harness before changing the ranker more.** Three parts, all cheap: (a) inter-run stability, Jaccard of picks and RBO of ranks over 5-10 repeats per fixed Search; (b) a silver set from an independent similarity source that is not used for candidates or scoring (Deezer `/artist/{id}/related` and Apple Music `similar-artists` are the best finds; use them offline only); (c) about 100-150 human pairwise judgments from the owner, used to calibrate an LLM judge and to sanity-check the silver set. Report precision@k and nDCG@k against the silver set, with the human set as the tie-breaker.
3. **If the LLM must score, make it a small ensemble with rank-level aggregation.** Score each candidate pointwise against a written rubric, with shuffled order, 3-5 runs, and aggregate by mean score or reciprocal rank fusion. Pairwise comparison (PRP) is more stable but costs more calls; use it only on the ambiguous band near the cut-off.

Not recommended now: building an own embedding graph from LB dumps, Wikidata/Discogs ingestion, setlist.fm co-billing storage, Spotify related-artists (gone for new apps).

Most important caveat: every usable similarity source (LB, Last.fm, Deezer, Apple) is built from listener behaviour, so they share popularity bias and they will agree with each other more than with a human who knows indie scenes. Agreement with a silver set measures consistency, not goodness. Ellis et al. found that human artist-similarity judgments vary a lot between people, so there is no single ground truth (ISMIR 2002, reference R9). Keep a human set.

## 1. Open artist-similarity and relationship data

### 1.1 Spotify (current status)

- Spotify's own blog post of 2024-11-27 says new Web API use cases lose Related Artists, Recommendations, Audio Features, Audio Analysis, featured/category playlists, 30-second previews and algorithmic/editorial playlists. It applies to new apps registered on or after that date and to dev-mode apps without a pending extension request; existing extended-mode apps are unaffected. Source: R1.
- I found no Spotify statement from 2025-2026 reversing this. A May 2026 third-party guide says the endpoints stay unavailable to new apps (secondary source, R2). A forum report says even an app with a pending extension request lost access; the blog does not say that (UNVERIFIED).
- Conclusion: treat Spotify related-artists as dead for this project. Also ADR 0003 bars sending Spotify account data to an LLM, so it was not a candidate input anyway.

### 1.2 ListenBrainz Labs similar-artists

- Endpoint family: `labs.api.listenbrainz.org/similar-artists`. The Labs index page only lists the viewer and does not document algorithms or parameters (R3).
- How it is computed (MetaBrainz developer reply, forum, not official docs): listens from the past 9,000 days are split per user into 300-minute sessions; every artist pair co-occurring in a session gets +1; per-session contribution is capped; low-scoring pairs are dropped. Only one algorithm dataset is live: `session_based_days_9000_session_300_contribution_5_threshold_15_limit_50_skip_30` (R4). A 2023 blog post shows an older name (`..._days_7500_..._threshold_10_limit_100_..._skip_30`), so the string has changed before; read it from the forum/doc before hard-coding (R5).
- Not tag-based. The forum thread says niche artists with few listeners can get no neighbours (a dungeon-synth example returned none) (R4). `11-artist-similarity-data.md` reports a refresh every Sunday per docs and an empty result for one 2025-26 act; I did not re-test.
- API rate limit (main ListenBrainz API, not stated for Labs): at most one call per second per client, 429 on excess, valid User-Agent with contact required (R6). Whether Labs follows the same limit is UNVERIFIED.
- Licence: ListenBrainz listens and text are CC0 and appear in public dumps (R7). Dumps: full twice a month, incremental more often; docs conflict on exact cadence (R7). Derived similarity from the Labs endpoint has no separately stated terms (UNVERIFIED), but cached top-N per MBID is the pattern already chosen in doc 11.

### 1.3 MusicBrainz

- Core data dump is CC0; derived/edit/stats archives are CC BY-NC-SA 3.0 (R8). Tags and genres are CC BY-NC-SA per doc 11.
- Rate limit: about 1 request/second per IP, identifying User-Agent required, else 503 (R10).
- Artist-artist relationship types (official list): member of band, subgroup, artist rename, artistic director, conductor position, founder, supporting musician, tribute, voice actor, collaboration, is person, teacher, artist-in-residence, plus personal relations (parent, sibling, married, involved with, named after) (R11). There is **no "influenced by"** relationship. Member-of and collaboration are useful as a precision-high signal ("same band lineage", "side project"), but coverage is thin for niche acts and they are not similarity.

### 1.4 Wikidata

- Structured data is CC0 (R12). Influenced-by is property P737, genre P136, record label P264 (property IDs from secondary listings, R13; P264 meaning UNVERIFIED on wikidata.org itself).
- Query service has a 60-second hard timeout and per-client processing-time limits (secondary source, R14). Dump is very large (doc 11: 104 GB json.bz2).
- Niche coverage is poor: many indie artists lack items or influence links (doc 11, my inference was not tested here). Use only as an optional lookup for the seed artist, not as a graph.

### 1.5 Last.fm

- Terms (R15): data for non-commercial use only; commercial use needs a separate agreement; cache according to HTTP headers; "Reasonable Usage Cap" of 100 MB stored; no sub-licensing; credit Last.fm and link to the catalogue page; Last.fm sets rate limits and you must not circumvent them.
- A public portfolio with no revenue is plausibly non-commercial, but "non-commercial" is not defined in the text I read; if you add affiliate links (see `10-affiliate-links.md`) the answer may change. UNVERIFIED whether affiliate revenue counts as commercial; ask partners@last.fm if in doubt.
- `artist.getSimilar` exists at `ws.audioscrobbler.com/2.0/` (R16 search result). Strong for mid-tier acts, weaker for tiny acts (doc 11, untested).

### 1.6 Deezer API (verified live, 2026-11-07)

- `GET https://api.deezer.com/artist/{id}/related` returned 20 related artists with no API key. For Khruangbin it returned Skinshape, Arc De Soleil, Common Saints, Sault, BALTHVS, Tommy Guerrero, El Michels Affair, Say She She, Holy Hive, Peter Cat Recording Co.; for Pinegrove it returned Slaughter Beach, Dog, Field Medic, Current Joys, Coma Cinema, Car Seat Headrest and others. Those look sensible, including for a small act (about 11k fans per `nb_fan`). This is a good independent signal.
- `GET /search/artist?q=` resolves names to Deezer ids. There is no MusicBrainz id in what I saw (UNVERIFIED whether any field carries one), so the join is by name, which adds matching error.
- How Deezer computes related artists: not documented (UNVERIFIED).
- Terms (R17): use "strictly limited for a non-commercial purpose and in a non-commercial environment"; content use limited to "a strictly private use within a family scope"; no numeric rate limit stated; Deezer may change or remove access at any time; caching is not addressed. A secondary source reports 50 requests per 5 seconds (UNVERIFIED). The "private family scope" wording means a public site that displays Deezer-derived results is on weak ground. Treat Deezer as **offline evaluation data, not a runtime source, and do not display it**.

### 1.7 Apple Music API

- Official docs define an `ArtistsSimilarArtistsView`; fetch with `GET /v1/catalog/{storefront}/artists/{id}/view/similar-artists` (R18). Needs a developer token from an Apple Developer Program account (cost UNVERIFIED; commonly stated as US$99/year, not confirmed here). Ranking, freshness and size of lists not documented in what I read. Terms for caching and display not checked: UNVERIFIED. Use for offline silver-set checks only unless the terms are read.

### 1.8 Discogs

- Monthly dumps of releases, artists, labels, masters in XML are CC0, though some data is restricted under API terms (secondary mirrors quoting Discogs, R19; I did not reach data.discogs.com itself). Gives labels, credits, aliases, members. No similarity. Large XML. Skip for now; label/credit overlap is a possible later feature (see 4).

### 1.9 AcousticBrainz

- Dead for new data. Collection stopped in 2022; site and API were still up at last check; data is CC0 with 29,460,584 submissions in archives dated 2022-07-06 (R20). Nothing new for 2025-26 artists, so useless for the niche/new-artist case.

### 1.10 Academic datasets

- **OLGA** (Korzeniowski, Oramas, Gouyon, ISMIR 2021): 17,673 artists, 101,029 AllMusic similarity relations, with AcousticBrainz features (R21). Journal version in TISMIR 2022 (R22). Licence and download location not confirmed (the paper says AllMusic data can be licensed from AllMusic; the PDF filename hints at CC BY for the paper only). UNVERIFIED whether it is redistributable. Frozen in time and AllMusic is editorial, so a good ground truth for general validation of a method but poor for 2025-26 indie acts.
- **aset400 / musicseer** (Ellis et al., ISMIR 2002): 400 US pop artists with survey-based ground truth (R9, R23). Old and mainstream; useful mainly as a methodological reference.
- **Million Song Dataset Last.fm dataset**: 943,347 matched tracks, 56,506,688 track-similar-track pairs, track level not artist level (R24). Download page and licence not confirmed (UNVERIFIED). Frozen 2011.
- **LFM-2b**: no longer downloadable for licence reasons (R25). **Music4All / Onion, Last.fm-1K, MLHD+**: not checked this round except as noted in doc 11 (MLHD+ non-commercial, frozen 2023-03; Music4All-Onion CC BY 4.0 per an aggregator, UNVERIFIED).
- **Jamendo**: not checked; catalogue is Creative Commons music, not a mainstream touring-artist set, so I judged it irrelevant. UNVERIFIED.

### 1.11 Every Noise at Once

- Still online but frozen. Glenn McDonald was laid off by Spotify on 2023-12-04 and lost access to the data; a Spotify spokesperson said the status would likely stay as is, with no new releases added (R26, secondary news coverage). No official API or download; scraping has terms risk. Not usable.

### 1.12 Setlist.fm (for the co-billing idea)

- Official API terms (R27): non-commercial only ("if the primary purpose of your application is to derive revenue, it is considered commercial"); must not retain copies of the data except cached for short periods; must make direct server calls; must display attribution. Terms page dated 2019 per search snippet. So a persistent co-billing graph built from setlist.fm violates the stated terms. Skip.

### Comparison table

| Source | What it gives | Access / cost | Rate limit | Licence / caching | Niche coverage | Status (2026-11-07) |
|---|---|---|---|---|---|---|
| ListenBrainz Labs similar-artists | MBID neighbours from listening sessions, scored | Free, no key; User-Agent with contact | 1 call/s on main API (R6); Labs limit UNVERIFIED | CC0 listen data (R7); Labs terms not stated; cache with TTL | Good down to thousands of listeners, empty below (R4) | Live; algorithm string has changed before |
| Last.fm artist.getSimilar | Name/MBID neighbours with match score | Free API key | Enforced, number not stated (R15) | Non-commercial; 100 MB cap; attribution; HTTP-header caching (R15) | Mid-tier good; tiny weak (doc 11) | Live |
| Deezer `/artist/{id}/related` | 20 related artists, no scores | No key (verified) | Unspecified; 50/5 s reported (UNVERIFIED) | Non-commercial, "private family scope"; caching unaddressed (R17) | Good on tested small act | Live; offline eval only |
| Apple Music `similar-artists` view | Related artists via relationship view | Developer token (fee UNVERIFIED) | Unchecked | Unchecked | Unchecked | Documented (R18) |
| Spotify related-artists | n/a | n/a | n/a | n/a | n/a | Removed for new apps since 2024-11-27 (R1) |
| MusicBrainz relationships | Member-of, collaboration, subgroup, etc.; no influence type | Free API / dump | ~1 req/s per IP (R10) | Core CC0, derived CC BY-NC-SA (R8) | Sparse for new acts | Live |
| MusicBrainz tags/genres | Crowd tags | Free | as above | CC BY-NC-SA (doc 11) | Sparse for new acts | Live |
| Wikidata P737/P136/P264 | Influence, genre, label | Free SPARQL or dump | 60 s query timeout (R14) | CC0 (R12) | Poor | Live |
| Discogs dumps | Labels, credits, aliases, members | Free monthly XML | n/a (dump) | CC0 with restricted fields (R19) | Weak | Live (not verified at source) |
| ListenBrainz listens dump | Raw listens, build own graph | Free, very large | n/a | CC0 (R7) | Best theoretical | Live; too big for 512 MB host |
| AcousticBrainz | Audio features | Free dumps | n/a | CC0 (R20) | None for post-2022 | Ended 2022 |
| OLGA | 17,673 artists, 101,029 AllMusic edges | Download location UNVERIFIED | n/a | UNVERIFIED | Mainstream, frozen | Static |
| aset400 / musicseer | 400 pop artists, survey ground truth | Academic page (R23) | n/a | UNVERIFIED | Mainstream only | Static, 2002 |
| MSD Last.fm dataset | Track-level similarity and tags | Download UNVERIFIED | n/a | UNVERIFIED | Frozen 2011 | Static |
| LFM-2b | Listening events | Not downloadable (R25) | n/a | n/a | n/a | Withdrawn |
| Every Noise at Once | Genre map | Website only | n/a | No API, scraping risk | Frozen | Online, frozen (R26) |
| Setlist.fm | Setlists, co-billing | Free key, non-commercial | Unspecified | No persistent caching (R27) | Good for touring acts | Live |

## 2. Verifying ranking quality without many labels

Ideas in order of how much I would trust them for this app:

1. **Inter-run stability (necessary, not sufficient).** Fix a set of 15-20 Searches and candidate lists, run the ranker 10 times, report mean pairwise Jaccard of the final picks and mean RBO of the ranked lists. RBO is designed for ranked lists that may not share the same items and weights the top more heavily; its parameter `p` sets top-weighting (Webber, Moffat, Zobel, ACM TOIS 2010, R28). Implementations exist, for example in PyTerrier (R28). Stability only says the ranker is consistent; a ranker that always returns the same bad list scores perfectly.
2. **Leave-one-source-out silver standard.** Generate candidates and the deterministic score from sources A (LB + Last.fm); evaluate the final picks against source B (Deezer related, Apple similar-artists) for each seed. Metrics: precision@8 and nDCG@8 where relevance is 1 if the picked artist appears in B's related list for any seed (or within two hops), else 0. Never score with a source that was used to produce the candidates or the score; that is circular and will reward whatever the candidate source already prefers. Also do the swap (A and B reversed) and compare. Large gaps flag source-specific behaviour.
3. **Graph agreement between sources.** For a sample of seeds, compute overlap of top-10 neighbours between LB, Last.fm and Deezer. Low agreement tells you the silver set is noisy for that seed; weight or drop those seeds. I found no standard citation for this exact procedure; it is my design.
4. **Small human set, used to calibrate.** Pairwise A/B judgments ("which of these two concerts is closer to what the Search asked for?") are faster and more consistent than absolute 0-100 scores. About 100-150 judgments across 15-20 Searches is enough to check whether the silver metric and an LLM judge agree with you at all (Spearman or Kendall tau; agreement rate on pairs). The sample size is a rule of thumb, not from a source.
5. **LLM-as-judge, calibrated.** Zheng et al. report strong position bias in pairwise judges and recommend swapping answer order and running twice; a strong judge agreed with humans over 80% of the time on their benchmarks, as often as humans agree with each other (R29, figures from secondary summaries; verify before quoting). Use a different model family or at least a different prompt from the ranker, swap order, and accept a verdict only when both orders agree. Do not use the same Claude call that ranks to judge its own output (self-preference). The follow-up "Judging the Judges" studies position bias across 15 judges (R30).
6. **Held-out co-listening.** You have no user data. Spotify account data cannot go to an LLM (ADR 0003); computing co-listening statistics from a user's own Spotify account without an LLM is not in scope. Skip.

Pitfalls:

- **Circularity.** Same source for candidates and scoring inflates scores. Keep candidate source and evaluation source disjoint, and say so in the report.
- **Shared popularity bias.** LB, Last.fm and Deezer are all co-listening based, so they agree on popular artists and all under-serve the long tail. Abdollahpouri et al. and a Last.fm-based replication (Kowald, Schedl, Lex, ECIR 2020) show recommenders favour popular items, and low-mainstream users get the worst results (R31, R32). Report metrics separately for popular and niche seeds.
- **Silver is not gold.** Ellis et al. found human similarity judgments vary widely (R9).
- **Threshold effects.** If you evaluate "picks >= 50", the metric will move when scores shift by a few points. Evaluate the ranking (top-k) too, not only the thresholded set.
- **Small n.** With 15-20 Searches, report confidence intervals or just the per-Search table; do not report a single decimal-place number as a result.

## 3. Making the LLM ranker stable

- **Temperature is not available on the current model.** Anthropic's Claude Sonnet 5.5 migration guide says sampling parameters return an error ("Remove `temperature`, `top_p`, and `top_k`") and lists them among five settings that return a 400 (R33). So determinism cannot be bought by lowering temperature. The remaining levers are the `effort` setting, prompt design, structured output, ensembling and post-processing. (Whether `effort` changes run-to-run variance is not documented in what I read; UNVERIFIED, test it with the stability harness.)
- **Sampling several runs and aggregating.** Self-consistency (Wang et al., ICLR 2023) samples multiple outputs and picks the most consistent; a small number of samples (5 or 10) captures most of the gain on reasoning tasks (R34). For scores, take the mean (or median) per candidate across k runs; for ranks, use reciprocal rank fusion (Cormack, Clarke, Buettcher, SIGIR 2009, score = sum of 1/(k+rank), k=60 in the paper; I did not open the PDF this session, details from memory, UNVERIFIED) or Borda count (R35). Cost: k times the ranker cost. With a 40-item shortlist this is small, but the budget is $10-15 per month total, so measure tokens per call first.
- **Pointwise vs pairwise vs listwise.** RankGPT uses listwise permutation generation with a sliding window and found it effective with GPT-4, with less consistency from weaker models (R36). PRP (Qin et al., Google, NAACL 2024) uses pairwise comparisons, reports strong results with modest models, and states it is insensitive to input order (R37). Pairwise needs O(n log n) to O(n^2) calls depending on the sort strategy, so for 40 candidates it is probably affordable only on the borderline band. Pointwise with a rubric is cheapest and works with any API but is the least stable; this is the current design.
- **Position bias and shuffling.** Pairwise judges favour the first position often (R29). For listwise or pointwise batches, shuffle candidate order per run and aggregate, so order effects average out instead of being systematic.
- **Rubric scoring.** Replace the free 0-100 with 4-5 anchored levels (for example 0 unrelated, 1 same broad genre, 2 shares tags or a similar-artist link at two hops, 3 direct similar-artist link, 4 direct link and shared descriptors). Coarse anchored levels reduce jitter versus a continuous number. This is general prompt practice, not from a cited experiment here.
- **Hybrid.** Deterministic score decides inclusion; LLM supplies (a) a veto for obvious mismatches (tribute act, wrong genre, wrong artist with the same name) and (b) the one-line reason. The reason must cite only fields that exist in the source record, per ADR 0002. This is the design with the largest expected stability gain, because the LLM no longer controls which items are in the top 8. Consider letting the LLM adjust the deterministic score within a narrow band (say +/-10) to break ties.
- **Cheaper stabiliser:** cache the ranker's output keyed by (normalised Search, candidate IDs, prompt version) so identical input returns identical output within a TTL. This removes visible variance for repeat visitors but does not make the ranker good.

## 4. Bold architectural options, ranked by value for cost

| Rank | Option | Value | Cost | Verdict |
|---|---|---|---|---|
| 1 | Deterministic score from LB + Last.fm (+ tags), LLM as veto and reason writer | High: stable, explainable, testable | Low: code change only | Do first |
| 2 | Evaluation harness: stability + leave-one-source-out silver set (Deezer/Apple offline) + 100 human pairs | High: lets you tell whether any change helps | Low to medium: scripts and about an hour of labelling | Do second, ideally before step 1 so you can see the gain |
| 3 | Ensemble of k runs with shuffling and mean/RRF aggregation | Medium | Low code, k times LLM cost | Only if the LLM still scores |
| 4 | Multi-source fused similarity score (LB, Last.fm, optional MusicBrainz tags) with per-source weights tuned on the human set | Medium to high | Medium | After 1 and 2 exist |
| 5 | Ticketmaster same-event co-billing as a signal (artists on one bill are often related) | Medium, free | Low if the feed already carries attractions; terms UNVERIFIED | Cheap experiment; use as a feature, test against the human set |
| 6 | Label / scene membership via Discogs or MusicBrainz | Low to medium; coverage thin for indie | Medium to high (large dump, entity matching) | Defer |
| 7 | Own artist embedding or co-occurrence graph from ListenBrainz dumps | Potentially best freshness and control | High: hundreds of GB, compute, ops; cannot run on small host | Not now |
| 8 | Setlist.fm / festival lineup graph | Medium signal | Terms bar persistent caching; non-commercial | Skip |
| 9 | Spotify related-artists, AcousticBrainz, LFM-2b, Every Noise | n/a | n/a | Dead or unavailable |

Notes on options 5 and 8: I did not verify what Ticketmaster's terms allow for using attraction co-occurrence; check before relying on it. Festival lineups from official sites would be scraped content with unknown terms; not assessed.

## Things I could not verify

- Whether the ListenBrainz Labs endpoint shares the main API 1 req/s limit, and its terms.
- Deezer related-artist algorithm, any MBID field, and whether displaying results is permitted (the written terms point to no).
- Apple Music similar-artists list size, ranking, caching terms and developer-program cost.
- OLGA, MSD Last.fm, aset400 download links and licences.
- Whether Last.fm treats affiliate-link revenue as commercial use.
- Whether Claude `effort` settings change run-to-run variance.
- RRF constant and formula (cited from memory; the PDF was not opened).
- Music4All-Onion, Last.fm-1K, MLHD+, Jamendo details beyond doc 11.
- Wikidata usage counts for P737/P136/P264.

## References

- R1 Spotify, "Introducing some changes to our Web API", 2024-11-27: https://developer.spotify.com/blog/2024-11-27-changes-to-the-web-api
- R2 Third-party guide on Spotify recommendation features (secondary): https://rapidevelopers.com/api-automations/how-to-automate-spotify-song-recommendations-using-the-api
- R3 ListenBrainz Labs index: https://labs.api.listenbrainz.org/
- R4 MetaBrainz forum, "How does similar artists work?": https://community.metabrainz.org/t/how-does-similar-artists-work/678642
- R5 MetaBrainz blog, GSoC 2023 artist similarity graph: https://blog.metabrainz.org/?p=10608
- R6 ListenBrainz API docs, rate limiting: https://listenbrainz.readthedocs.io/en/latest/users/api/index.html
- R7 ListenBrainz data dumps docs: https://listenbrainz.readthedocs.io/en/latest/users/listenbrainz-dumps.html
- R8 MusicBrainz database download and licences: https://musicbrainz.org/doc/MusicBrainz_Database/Download
- R10 MusicBrainz rate limiting: https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting
- R11 MusicBrainz artist-artist relationship types: https://musicbrainz.org/relationships/artist-artist
- R12 Wikidata licensing: https://www.wikidata.org/wiki/Wikidata:Licensing
- R13 Wikidata property lists (secondary): https://www.wikidata.org/wiki/Help%3AFrequently_used_properties/en
- R14 Wikidata Query Service limits (secondary): https://en.wikibooks.org/wiki/SPARQL/Printable_version
- R15 Last.fm API Terms of Service: https://www.last.fm/api/tos
- R16 Last.fm artist.getSimilar (existence, via search): https://www.last.fm/api/show/artist.getSimilar
- R17 Deezer API terms of use: https://developers.deezer.com/termsofuse
- R18 Apple Music API, similar-artists view: https://developer.apple.com/tutorials/data/documentation/applemusicapi/artists/views-data.dictionary.md
- R19 Discogs data dump licence (secondary): https://blog.archive.org/2020/12/06/discogs-thank-you-a-commercial-community-site-with-bulk-data-access/
- R20 AcousticBrainz download and end of project: https://acousticbrainz.org/download and https://community.metabrainz.org/t/acousticbrainz-making-a-hard-decision-to-end-the-project/572828
- R21 Korzeniowski, Oramas, Gouyon, "Artist Similarity with Graph Neural Networks", ISMIR 2021: https://arxiv.org/abs/2107.14541
- R22 "Artist Similarity for Everyone", TISMIR 2022 (listing): https://doaj.org/article/3d00d5df750046eaad6075feef48b784
- R23 Dan Ellis, music similarity project (aset400): https://www.ee.columbia.edu/~dpwe/research/musicsim/index.html
- R9 Ellis, Whitman, Berenzweig, Lawrence, "The Quest for Ground Truth in Musical Artist Similarity", ISMIR 2002: https://ismir2002.ismir.net/proceedings/02-FP05-4.pdf
- R24 Million Song Dataset Last.fm dataset announcement: https://auditory.org/postings/2011/794.html
- R25 LFM-2b page (not downloadable): https://www.cp.jku.at/datasets/LFM-2b/
- R26 Billboard Canada on Glenn McDonald and Every Noise (secondary): https://ca.billboard.com/business/streaming/spotify-s-former-data-alchemist-gives-every-song-a-genre
- R27 setlist.fm API terms: https://www.setlist.fm/help/api-terms
- R28 Webber, Moffat, Zobel, "A Similarity Measure for Indefinite Rankings" (RBO), ACM TOIS 2010: https://people.eng.unimelb.edu.au/ammoffat/abstracts/wmz10acmtois.html ; PyTerrier RBO: https://pyterrier.readthedocs.io/en/latest/ext/pyterrier-alpha/rbo.html
- R29 Zheng et al., "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena": https://arxiv.org/abs/2306.05685
- R30 "Judging the Judges: A Systematic Study of Position Bias in LLM-as-a-Judge": https://arxiv.org/abs/2406.07791
- R31 Abdollahpouri and Mansoury, popularity bias and exposure metrics: https://arxiv.org/pdf/2007.12230
- R32 Kowald, Schedl, Lex, "The Unfairness of Popularity Bias in Music Recommendation: A Reproducibility Study": https://arxiv.org/abs/1912.04696
- R33 Anthropic, Claude Sonnet 5.5 migration guide: https://platform.claude.com/docs/en/models/sonnet-5-5/migration-guide
- R34 Wang et al., "Self-Consistency Improves Chain of Thought Reasoning": https://arxiv.org/abs/2203.11171
- R35 Cormack, Clarke, Buettcher, "Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods", SIGIR 2009: http://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf (not opened this session)
- R36 Sun et al., RankGPT, "Is ChatGPT Good at Search?": https://arxiv.org/abs/2304.09542 ; code https://github.com/sunnweiwei/RankGPT
- R37 Qin et al., "Large Language Models are Effective Text Rankers with Pairwise Ranking Prompting": https://arxiv.org/abs/2306.17563
- Internal: `docs/research/11-artist-similarity-data.md`, `docs/research/06-spotify-alternatives.md`
