# Spotify personalization beyond five friends

November 7, 2026. Research only. This supersedes the product recommendation to lead with manual Artist entry in the [account design](2026-11-07-account-experience-design.md). The owner wants actual Spotify-based personalization; Last.fm and ListenBrainz are not suitable substitutes for friends who do not use them.

## Finding

Multiple client IDs are now available, but pooling them for one Concert Scout application conflicts with an explicit Spotify rule. A managed music-library integration is a technically relevant commercial lead, with a prohibitive published minimum and an unresolved permitted-use question. A user-directed Spotify-to-CSV export is the strongest low-budget candidate found: it brings real Spotify library data without manual Artist entry or waiting for Spotify's privacy archive. It is an import, not continuous account sync, and needs real-device validation before product commitment.

I did not establish an inexpensive, supported, public one-click Spotify connection for an individual developer. The earlier account design should remain on hold while we decide whether an import preserves enough of the intended experience.

## Multiple Spotify apps: the precise answer

Spotify's February migration guide still says one client ID. Its **July 23, 2026 update** raises that to **25 client IDs per developer**, but combines their API usage into one developer-account quota. The current quota page still limits development apps to five allowlisted users. API request quota and authorized-user count are separate limits. [July update](https://developer.spotify.com/blog/2026-07-23-web-api-quota-updates), [quota modes](https://developer.spotify.com/documentation/web-api/concepts/quota-modes), [older February guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide).

The missing constraint is in Developer Terms VI.1 and Developer Policy VII: **“You may not use more than one Security Code for each SDA.”** The policy identifies the client ID as that security code. This is a direct rule, not an inference from shared request quotas. Running several app registrations and routing groups of friends to them would use several IDs for the same website. Separate names, callback routes or domains would not establish separate products by themselves. [Developer Terms](https://developer.spotify.com/terms), [Developer Policy](https://developer.spotify.com/policy).

Conclusion: do not sell the 25 × 5 arithmetic as a supported 125-person Concert Scout plan. We could ask Spotify whether it will explicitly permit several client IDs for a small, noncommercial friends beta, but no such permission was found. No support inquiry has been sent.

Other variants do not establish a solution:

- **Several developer accounts:** changes who holds credentials, not that Concert Scout is one application. Also adds Premium and credential-management dependencies.
- **Each friend supplies a client ID:** reasonable to investigate for independent, self-hosted personal installations, but poor onboarding for this shared website and not an established exception to the single-application rule. Each developer owner needs Premium.
- **Rotate five people through the allowlist:** not a demonstrated persistent-connection design. Do not promise continuing refresh/access for users removed from the list or retained data as a substitute for authorization.
- **PKCE, another OAuth library or Supabase Spotify login:** change authentication implementation, not the upstream access limits.

## Option 1: a managed Spotify integration

[MusicAPI](https://musicapi.com/spotify-api), operated by the team behind FreeYourMusic, advertises hosted sign-in, library reads and a user identifier for subsequent calls, without managing our own Spotify client. Its documented library includes liked tracks, followed Artists and playlists. It describes itself as a **transfer layer**, not a general proxy. A top-Artists listening-history endpoint and unrestricted ongoing concert personalization were not established. Its sandbox is five test listeners, so the free sandbox is not a public-access solution.

The [billing documentation](https://musicapi.com/docs/billing/billing-and-usage) says managed integrations have a **€500/month minimum**. Bringing only our own developer apps avoids that minimum, but does not solve Spotify's five-user restriction. A smaller per-request headline price is therefore misleading for this use case.

This is a vendor lead, not a confirmed approved integration for Concert Scout. Before buying or integrating, get written answers on: permission for a concert-discovery destination rather than streaming-service migration; official Spotify access/authorization basis; data available beyond library membership; permitted refresh/retention; attribution and deletion; and a hobby/portfolio price. No vendor was contacted, no trial account created, and no price concession is assumed.

If a suitable agreement is available, the product could keep a hosted **Connect Spotify** redirect and automatic library import. Our server would receive minimal Artist data, match it deterministically to source Concerts and keep it outside model paths. A provider does not remove [ADR 0003](../adr/0003-official-spotify-access-only.md).

## Option 2: connect Spotify in an export tool, import its file here

[TuneMyMusic's Spotify-to-file page](https://www.tunemymusic.com/transfer/spotify-to-file) documents connecting Spotify, choosing playlists/liked songs/albums/Artists and exporting CSV or TXT with no destination streaming account. Its [help page](https://www.tunemymusic.com/help) currently advertises free transfers and TXT/CSV exports up to 500 tracks. This is a user-operated external service, not our application's borrowed OAuth client. Exact limits, consent scopes, file schema and actual mobile flow still need acceptance testing.

Proposed experience:

1. Concert Scout offers **Bring your Spotify music** with two explicit choices: invited direct connection, or **Import from Spotify with TuneMyMusic**.
2. Explain the external step: **Connect Spotify, export some Liked Songs or a playlist you made, then bring the file back here.** Link directly to the export workflow; never label it a direct Concert Scout connection.
3. The person authorizes TuneMyMusic and chooses their own music. No Last.fm account, retyping Artists, or weeks-long history-export wait is required by this documented path. Whether a separate TuneMyMusic account is required must be tested.
4. Back in Concert Scout, upload or paste the export. Parse it locally, show the actual extracted Artists for confirmation, discard the raw track file and match Artists to nearby Concerts in code.
5. A Supabase account can preserve the chosen import and Saved Concerts, subject to documented provenance and retention. UI says **Imported from Spotify on [actual date]** and **Update import**; it never claims a live connection or silently refreshes.

This contains two handoffs and a file. It is materially more friction than the original Connect Spotify button. A liked-song or playlist selection also differs from Spotify's top-Artists listening signal. We must test whether it feels good enough rather than redesign the product around an untested assumption.

Use a playlist the person made or their own library selection. Do not assume Spotify-generated playlists such as Discover Weekly/Daily Mix can be exported. Existing [list parsing](../../frontend/lib/taste-files.ts) supports several Artist column labels but does not establish compatibility with a real TuneMyMusic export, which was not downloaded here.

Keep a new source provenance for this import and route its Artist list through the deterministic shelf initially. Do not automatically treat an API-derived intermediary CSV as the legally distinct, user-held privacy archive already discussed in the Taste spec. No Spotify-to-model path should be introduced by changing the transport to a file. Long-term storage and deletion rules need review before implementation; a file is not permission to retain everything indefinitely.

## Other ideas checked

| Idea | What the evidence establishes | Fit |
|---|---|---|
| Soundiiz API | Creator API keys are scoped to the account that created them; the separate public endpoint sends a tracklist into Soundiiz | Not a drop-in way to read every friend's Spotify library using our one key |
| Spotify privacy download | Official account export includes library/Artist information and listening history | Real option, already supported in part, but unsuitable as instant first-run onboarding |
| Spotify Soloist | Official local playback client with queue/playback metadata; each user needs setup and a key | Could support a separate local companion concept; does not establish access to top Artists or a website-only onboarding solution |
| Musicfetch | Public product is a metadata/link-resolution API | Artist/track lookup is not authorization to read someone's private listening Taste |
| Screenshot/local OCR | Could extract a user-selected Artist list with local OCR and confirmation | Untested import experiment; not equivalent to a connected library or continuous sync |
| Scraping web-player tokens/internal APIs | Requires an unofficial access path | Conflicts with ADR 0003; not a reliable public portfolio foundation |

Sources: [Soundiiz API limits](https://support.soundiiz.com/hc/en-us/articles/37958897763730-Soundiiz-API-Access-Creator-API-Key-and-Public-Playlist-Import), [Spotify export contents](https://support.spotify.com/us/article/understanding-your-data/), [Soloist overview/access](https://developer.spotify.com/documentation/soloist), [Musicfetch](https://musicfetch.io/). Screenshot OCR is an engineering possibility, not a verified existing flow.

## Recommended next decision and proof

Preserve Spotify as the personalization goal. Do not implement the manual-first account design as if that goal were resolved.

For the existing budget, first validate a real TuneMyMusic export on desktop and iPhone: actual cost, accounts/consent, time and steps, exported Artist columns/multiple-Artist handling, selected-music quality, local parsing and deterministic source-backed Concerts. Include one friend outside our Spotify allowlist. The success condition is personalized Concerts from their actual Spotify music without developer setup or typing Artist lists. No mobile timing or successful export is claimed in this research.

If that handoff is too much friction and one-click live connection is essential, the unresolved dependency is access: written Spotify permission/extended access or an explicitly permitted, affordable managed integration. A polished account system alone cannot fix it. Prepare the concrete noncommercial use case and questions above for an owner-approved inquiry; do not send unsolicited messages.

Research performed in one agent. No production code, credentials, provider accounts, allowlists, messages, subscriptions or deployments changed.

## Follow-up: third-party and unofficial APIs

The owner explicitly asked whether unofficial APIs could replace direct Spotify access. Yes, concrete implementations exist. Their access model matters more than their API label; the following are documented capabilities, not independently successful live tests.

| Candidate | Documented access | Product implication |
|---|---|---|
| [Aran404/SpotAPI](https://github.com/Aran404/SpotAPI) | Python wrapper emulating the Spotify browser; public/private operations, account login and cookie imports | Technically relevant to library access, but not a normal limited-scope OAuth replacement. Its author labels it educational and warns about Spotify terms. |
| [carlelieser/spot-api](https://github.com/carlelieser/spot-api) | Concrete SpotAPI HTTP proxy exposing saved tracks and library playlists using a user's Spotify session cookie | Strong evidence that a private-library integration can be built, not proof it is reliable or approved. The described design forwards a browser session credential to a server. |
| [NTifyApp/NTify-SpotAPI](https://github.com/NTifyApp/NTify-SpotAPI) | Java implementation of internal client APIs, including library and playlist operations | Requires genuine access/client tokens supplied separately; does not solve sign-in itself. |
| [Apify aolmo/spotify-playlist](https://apify.com/aolmo/spotify-playlist) | Vendor advertises public playlist/album/track reads without login or a Spotify API key | Enables a candidate paste-playlist-link flow. Vendor documents a 50-track playlist cap and no private playlist reads. It cannot expose a person's private Liked Songs or listening history. |
| [ScrapingBee Spotify pipeline](https://github.com/ScrapingBee/spotify-api) | Public metadata pipeline; its own README excludes private-library reads and credentialed scraping | Another public-playlist lead, not a private account connection. |

The practical distinction: a friend can share a public playlist they made and receive deterministic Concert matches from its Artists, without typing names or moving a file. That is a more convenient experimental import than CSV, but only uses that playlist's music. It is not equivalent to connecting the entire Spotify account. Private Liked Songs would need a separate user-controlled export or account-access method.

Potential public-link flow: accept an explicitly shared playlist URL; validate the URL/ID and retrieve only bounded metadata through a chosen vendor; show actual extracted Artists and any truncation; match source Concerts deterministically; retain Spotify provenance and attribution. Do not accept arbitrary fetch URLs, claim full coverage for a truncated list, download audio or send the metadata to a model. No provider key, paid run or new implementation was created for this research.

Public accessibility and a vendor subscription do not establish Spotify permission. The repo's existing ADR 0003 rejects unofficial access, so a production scraping path would require an explicit architectural decision addressing that conflict. Private-cookie integration is a larger change: session credentials grant broader access than the application's read-only OAuth scopes, revocation and expiry are less controlled, and internal interfaces can change. A local-only experimental importer might reduce server exposure, but is not a verified implementation or an established terms exception.

Recommended evaluation if the owner wants an unofficial route: assess a public-playlist-link prototype first. Its user experience can be tested without collecting friends' Spotify session cookies. If the requirement remains automatic full private-library or top-Artists access, SpotAPI is the relevant technical research target, with the authentication and existing-policy tradeoffs stated plainly. Hosted MusicAPI remains a separate paid lead; its transfer-use restrictions still require confirmation.
