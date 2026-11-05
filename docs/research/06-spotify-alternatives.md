# 06 - Spotify limits: alternatives and workarounds (as of 2026-11-04)

Builds on `01-data-sources.md`; the Dev Mode cap, Premium owner, playlist-read rule and AI ban are not repeated here. Evidence came from web search and page fetches on 2026-11-04. Anything not confirmed is marked UNVERIFIED. Search snippets and third-party blogs are weaker evidence than Spotify's own pages; each claim says which it is.

## Bottom line

The limits are not "gotten around" by any legitimate open-source project. Projects either (a) stop using the Spotify API and take user-supplied data, (b) make each user bring their own Client ID, which still hits the 5-user cap, or (c) use unofficial access that Spotify's terms forbid. For Concert Scout, the best answer is to treat Spotify as an optional, user-initiated import and not as the taste backbone.

### Top 3 (all compliant)

1. **Last.fm username (and ListenBrainz username), no Spotify API.** `user.getTopArtists` needs only an API key, no user auth, with periods overall/7day/1month/3month/6month/12month (https://www.last.fm/api/show/user.getTopArtists, fetched 2026-11-04). It reveals Spotify taste only for users who already scrobble Spotify to Last.fm. Free for non-commercial use (see 01).
2. **User-uploaded Spotify data export (Extended Streaming History JSON), parsed in the browser.** It works for any Spotify user, free or Premium, with no app registration, and the file never has to leave the device. Cost: a wait of days to weeks, and a clunky first-run flow.
3. **Pasted artist lists / Exportify-style CSV / screenshot read by the user (not by us)**: lowest friction, no dependencies, fully compliant. Weaker data, since the user types or pastes it.

Runner-up for owner and up to 4 friends only: normal Spotify OAuth in Dev Mode, as already noted in 01.

### Compliant vs ToS-violating at a glance

| Compliant | Grey or unclear | Violates Spotify terms / circumvents controls |
|---|---|---|
| Last.fm and ListenBrainz usernames; privacy export upload; pasted lists; CSV; user's own screenshots; oEmbed for named items; Apple/Google exports | Bring-your-own Client ID (legal per user, but it moves the problem to the user); Odesli; transfer sites as a user-side step | librespot-based access; SpotAPI; web-player token scraping; spotipy-anon style anonymous access (see 4); spotDL; multiple Client IDs to dodge the 5-user cap |

---

## 1. User-owned flows (no Spotify API)

### 1a. Privacy data export (Extended Streaming History / Account Data)
- **How it works:** the user requests it on Spotify's Privacy page ("Download your data"). Guides say to untick "Account data" and select only "Extended streaming history", then confirm through an emailed link. A ZIP of JSON arrives (`Streaming_History_Audio_*.json` or older `endsong_N.json`) plus a "Read Me First" file describing the fields. The basic Account Data export has a different, shorter format (`StreamingHistory*.json`). Sources: https://freeyourmusic.com/blog/spotify-extended-streaming-history (Oct 2026), https://takeoutday.org/guides/download-spotify-data (undated), https://mystats.music/guides/spotify-extended-history (undated), https://spotify-devs.github.io/echostats/user-guide/importing-history/ (undated).
- **Works today:** yes per multiple 2026-dated or current third-party guides and tools (stats.fm/Spotistats, Trackify, EchoStats, Strata all document importing it). Spotify's own page: https://support.spotify.com/ca-en/account_payment_help/privacy/understanding-my-data/ (not read in full; UNVERIFIED for exact field list).
- **Wait time:** conflicting. Guides say 1 day to 30 days. The basic export's coverage (30 days vs 1 year) also conflicts across sources: UNVERIFIED.
- **Maintenance / ecosystem:** many independent importers exist. ListenBrainz has no native importer; PR https://github.com/metabrainz/listenbrainz-server/pull/1800 was still open in search results and a 2025 forum thread says it was planned but not added (https://community.metabrainz.org/t/can-the-spotify-integration-also-import-full-history/681254). Community converters exist (elbisaur on JSR, GitLab scripts). stats.fm import needs Plus (per its own guide, https://support.spotistats.app/docs/import/spotify-import; may have changed).
- **Fragility:** low for a parser that reads only artist and play-duration fields; Spotify has changed file names before, so parse by glob and tolerate missing fields. Filter plays under 30 s and skipped tracks, as stats.fm and elbisaur do.
- **ToS:** compliant. It is the user's own personal data delivered under privacy rights; we never touch the Spotify API or Spotify Content. Treat the file as user-provided personal data: parse in-browser, send only an aggregated artist list (name, play count, last played) to the server, and say so in the UI. Whether "Spotify Content" rules apply to user-supplied exports is a legal grey point; I found no clause covering it (UNVERIFIED).
- **AI caveat:** the Developer Policy AI ban (see 01) applies to Spotify Platform and Content. Data from the user's own export does not come through the Platform, so passing artist names to an LLM is lower risk, but this is my reading, not legal advice. Safer: use the artist list only for Last.fm/MusicBrainz lookups and give the LLM structured, non-Spotify data.
- **Fit:** good. Slow for first use, so it suits power users, not a casual "type your name" flow.

### 1b. Pasted artist lists
Compliant (user's own words), zero fragility. Already the fallback in 01. Fit: good, as the guaranteed floor.

### 1c. Screenshot of a playlist read by vision
- **How:** user uploads a screenshot; a vision model extracts artist/track names.
- **Works today:** technically yes (generic capability); no Spotify-specific evidence searched. UNVERIFIED for accuracy on dense or scrolling playlist screens.
- **ToS:** no access control involved and Spotify's servers are not touched. But sending a Spotify UI screenshot to an AI model arguably "feeds Spotify content to AI" under the Developer Policy spirit. The policy binds developers using the Spotify Platform; a user's own screenshot is outside the Platform, so exposure is low but not zero. Flag to owner as a judgement call; if wanting zero risk, skip this.
- **Fit:** poor to moderate. Cost, error rate and the policy question outweigh the gain over pasting text.

### 1d. Spotify Wrapped screenshots
Same analysis as 1c; only about 5 top artists, once a year. Fit: poor.

### 1e. Exportify-style CSV
- **How:** Exportify (https://github.com/delight-im/exportify) uses the Web API in the user's browser to export playlists to CSV. Its README suggests registering your own Client ID if you hit rate limits. I could not confirm whether it has been updated for the 2026 changes (search found no Exportify-specific 2026 notice). UNVERIFIED that the hosted copy still works for non-allowlisted users; under Dev Mode rules it would not, and playlists the user does not own or collaborate on return no items.
- **What we would accept:** a CSV the user already has (from Exportify run with their own Client ID, TuneMyMusic, Soundiiz or elsewhere). Parse locally; read only the artist column.
- **ToS:** accepting a file is compliant. How the user made it is their business.
- **Fit:** good as an additional accepted file type, low cost.

---

## 2. Bring-your-own Client ID (BYO, PKCE)

- **How:** each user registers their own Spotify developer app, pastes the Client ID into the tool, and the tool runs Authorization Code with PKCE in the browser (no secret). Each user is then the owner and sole allowlisted user of their own app.
- **How projects coped in 2026:** one concrete example: FullStop removed its hardcoded shared Client ID on 2026-02-11 and made BYO required, citing the 5-user cap (https://github.com/adv-inn/FullStop/pull/14, fetched 2026-11-04; the PR text had a year typo, so treat the date as the merge date shown). Spotify's community forum has developers asking whether multiple Client IDs to onboard testers is allowed, with no official answer found (https://community.spotify.com/t5/Spotify-for-Developers/Question-about-Development-Mode-user-limits-multiple-Client-IDs/td-p/7554284). Spotify-tui successors, Stats for Spotify-like tools: I did not find sourced evidence of how specific ones adapted (UNVERIFIED); do not assume.
- **Hard blockers for a public web app:**
  - The developer account must have Premium (per 01), so every BYO user must pay for Premium. That excludes free users.
  - Quotas are now per developer account (July 2026 changelog, per 01), so each user's own account has its own pool. This is the one thing that helps.
  - Playlist contents are readable only for owned/collaborative playlists. Top artists (`/me/top/artists`) is the useful endpoint; I did not verify it is still available to new Dev Mode apps. UNVERIFIED.
  - Friction is very high: create a developer account, create an app, set redirect URI, paste ID.
- **Terms:** Developer Terms VI.1.2 says one Security Code per app and VI.1.3 forbids sharing credentials (https://developer.spotify.com/terms, fetched 2026-11-04). A BYO design where each user owns their own app is consistent with that. The one that violates it is **you** creating many Client IDs to onboard more than 5 users: Spotify's one-Client-ID-per-developer limit (raised to 25 in July 2026) plus the per-account quota means this is the cap being evaded, which I would treat as circumvention of a technical/commercial control. Do not do this.
- **Maintenance / fragility:** depends on a Spotify rule set that changed twice in 2026. High fragility; Spotify can tighten the Premium and cap rules again.
- **Fit:** poor for a general audience. Acceptable only as an "advanced users" option; the data export is easier.

---

## 3. Bridges

| Bridge | How it reveals Spotify taste | Works today? | ToS / circumvention | Fit |
|---|---|---|---|---|
| Last.fm linked to Spotify | User connects Spotify in Last.fm settings; plays are scrobbled; a public profile exposes top artists by username | Appears to work: a 2018 MakeUseOf guide and a UK newspaper piece describe it; no 2026 Last.fm help page was confirmed (UNVERIFIED current steps). Last.fm API call itself verified 2026-11-04 | Compliant. We call only Last.fm. Last.fm API terms are non-commercial (01). Private profiles return nothing; not every Spotify user scrobbles | Best. Rank 1 |
| ListenBrainz | Users can link Spotify to it via ListenBrainz's own Spotify integration (UNVERIFIED current scope; forum says full-history import is not built in). Public stats by username | Partially. Native history import missing as of 2025-26 | Compliant; open data. Small audience | Good secondary |
| stats.fm (Spotistats) | Closed app; shows Spotify stats; has an API but I found no public, supported API for third parties (UNVERIFIED) | Import of export needs Plus per its guide | Scraping their profile pages would be against their terms (not read: UNVERIFIED). Not an integration path | Poor. Link to it as a user tool only |
| TuneMyMusic | User-side playlist transfer. Spotify's own "import playlists" feature is reported to be built on TuneMyMusic (https://dataconomy.com/2025/11/24/playlist-migration-arrives-on-spotify-months-after-apples-debut/, Nov 2025; secondary source). Can export a playlist to a file for a user | Works as a user tool. Free limits conflict across sources (500 vs unlimited tracks): UNVERIFIED | Spotify has historically threatened services that help users leave (2020: https://appleinsider.com/articles/20/10/12/spotify-reportedly-threatens-developers-over-transferring-playlists-to-other-services). We would not be integrating; just accepting the file | Poor as an integration; fine as a hint to users |
| Soundiiz | Same as TuneMyMusic. Free limit reportedly 200 tracks (competitor claim, UNVERIFIED) | As above | As above | Poor |
| Odesli / song.link | Cross-platform link resolver: given a Spotify URL, returns links on other services. It does not return taste. Third-party clients cite 10 req/min unauthenticated, higher with a key (UNVERIFIED; no official page found) | Probably works | Official terms not found (UNVERIFIED). Resolves metadata, adds no taste data | Not useful for taste. Maybe for linking out |

---

## 4. Public-web methods (risk assessment only)

No access instructions are given. Summary of status:

| Method | What it does | Status | Terms / control circumvention | Reliability |
|---|---|---|---|---|
| **oEmbed** | `GET https://open.spotify.com/oembed?url=<spotify url>` returns JSON: `title`, `html` (iframe pointing to `open.spotify.com/embed/...`), `thumbnail_url` (+ width/height), `type` "rich", `version`, `provider_name`, `provider_url`. Accepts show, episode, artist, album, track URLs. No auth or limits stated (https://developer.spotify.com/documentation/embeds/reference/oembed, fetched 2026-11-04) | Official, documented, working | **Compliant** as intended (embed). It gives only a title and thumbnail; no genres, popularity or playlist contents, so it cannot enumerate a playlist | Stable. Rate limits not documented (UNVERIFIED) |
| **Embed page** (`open.spotify.com/embed/...`) | The iframe widget. Playing it is the intended use. Extracting data from its HTML/JS to read playlist tracks is a different thing | Documented as an embed only | Using it to display: compliant. Programmatically scraping its payload for data: against Developer Terms IV.2.4.1 (bots, crawlers to "retrieve, duplicate, or index" content) if you are an SDA developer; also inconsistent with the embed's purpose. Treat as **not compliant** | Fragile; markup is undocumented |
| **open.spotify.com HTML metadata** | Public pages carry Open Graph tags (title, description, image) for sharing | Works; not a supported API | Reading OG tags of a URL the user pasted, one at a time, is low risk but still automated retrieval by a bot; Spotify's end-user terms (fetched 2026-11-04) contain no explicit scraping clause, but they bind use to what the Agreements permit, and the Developer Terms bar crawlers (above). Grey, lean avoid | Fragile |
| **Web-player token scraping** | Obtaining the anonymous or logged-in web-player token to call internal endpoints | Used by several libraries below | **Violates** Developer Terms (using robots to retrieve content, bypassing the Dev Mode controls the policy builds on) and almost certainly the end-user terms; it circumvents technical controls. Do not use | Breaks frequently; accounts can be banned (UNVERIFIED for specific bans) |
| **spotipy-anon** | Extension to spotipy for anonymous Web API access. PyPI latest release 2025-11-07, mirror updated 2026-05-12 (https://pypi.org/project/spotipy-anon/) | Exists; whether it still works after Feb 2026 is UNVERIFIED | Relies on anonymous web-player access; same assessment as token scraping | Fragile |
| **SpotAPI / SpotipyFree** | Python wrapper emulating browser requests to public and private Spotify endpoints; no key, no Premium. README itself warns it "may violate Spotify's terms of service" and calls it a proof of concept; GPL-3.0; async rewrite in beta; optional CAPTCHA-solver use (https://github.com/Aran404/SpotAPI, fetched 2026-11-04) | Active-ish; works status UNVERIFIED | **Violates** terms by its own README; CAPTCHA solving is explicit circumvention. Do not use | Fragile |
| **librespot** | Open-source Spotify Connect client (Rust). Premium only. README: "Using this code to connect to Spotify's API is probably forbidden by them. Use at your own risk." (https://github.com/librespot-org/librespot, fetched 2026-11-04). Active org fork; original unmaintained | Works for playback clients | Reverse-engineered protocol; not a taste-data source for us. **Violates** terms per its own README. Do not use | Moderate |
| **spotDL** | Reads Spotify metadata, then downloads matching audio from YouTube via yt-dlp. 26.6k stars, 3,000+ commits, 2026 footer so it appears maintained (https://github.com/spotDL/spotify-downloader, fetched 2026-11-04). README disclaims user legal responsibility | Active | A music downloader. Developer Terms IV.2.2.3 bars facilitating "stream ripping". Copyright issues for downloads. Irrelevant to taste and unsafe to touch | Active but legally dubious |

**Plain statement for the owner:** every method in this table other than oEmbed and a user-supplied export either violates Spotify's terms or works by getting around the access controls that Spotify put in place in 2024 to 2026. Spotify's posture is documented: the Developer Policy and Terms (https://developer.spotify.com/policy and /terms) and the Feb 2026 post (https://developer.spotify.com/blog/2026-02-06-update-on-developer-access-and-platform-security) show they are tightening, not loosening. For a portfolio app tied to your name and your Spotify developer account, the risk is app/account revocation, and a reputational cost in a portfolio, and I found no evidence of litigation against small hobby users (UNVERIFIED either way). Recommendation: do not use any of these.

---

## 5. Other platforms' equivalents

| Source | How | Works today | Notes / ToS | Fit |
|---|---|---|---|---|
| **Apple Music** | privacy.apple.com "Request a copy of your data" > Apple Media Services (limited to this to avoid stalls per one user report); multi-part ZIPs. Apple's separate playlist transfer tool supports only YouTube Music as destination (https://support.apple.com/120030) | Request path exists; the file layout inside the ZIP is UNVERIFIED (search found only a third-party note, https://notes.billmill.org/music/data_export/Apple_Music_GDPR_Export.html, not read). Third-party guide: https://mystats.music/guides/apple-music-history | User-owned data; compliant. Apple's MusicKit route needs a paid developer account (see 01) | Moderate: accept as upload, after verifying the file layout |
| **YouTube Music via Google Takeout** | takeout.google.com > YouTube and YouTube Music. Playlists export as CSV with video ID and timestamp only (little metadata); watch history as JSON (`watch-history.json` with titles, video IDs, timestamps). Google also has a "copy playlists to another service" flow (https://support.google.com/accounts/answer/14792019) | Works per third-party guides; formats UNVERIFIED for 2026. Artist mapping is weak (video titles, "Topic" channels) | User-owned; compliant. Needs title parsing and MusicBrainz matching | Low priority; accuracy poor |

---

## Suggested ranking of build work (layered, per owner's preference)

1. Manual artist entry (done / baseline).
2. Last.fm username import.
3. File upload (Spotify Extended Streaming History JSON, Exportify/TuneMyMusic CSV), parsed client-side, reducing to artist, plays and last-played.
4. ListenBrainz username.
5. Optional Spotify OAuth for the owner and up to 4 allowlisted users; label it as such.
6. Defer Apple and Google exports until someone asks.

Do not build: BYO Client ID as a primary path, anything in section 4 beyond oEmbed, multi-Client-ID tricks.

## What I could not verify
- Current Last.fm help page for Spotify scrobbling (2026).
- Whether the Exportify hosted site and `/me/top/artists` still work for new Dev Mode apps.
- Exact field names in the 2026 export files, and basic-export coverage period.
- Odesli, stats.fm, TuneMyMusic and Soundiiz official terms and API access.
- Whether spotipy-anon, SpotAPI and the other unofficial libraries still function after Feb 2026, and any DMCA or enforcement history for spotDL/librespot (search returned nothing).
- Apple Media Services export file layout and current Google Takeout YouTube Music formats.
- Spotify Hacker News/Reddit threads: the searches returned no relevant HN/Reddit hits, so those channels are not represented; the community-forum threads are cited instead.
