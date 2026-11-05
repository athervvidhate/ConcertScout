# 07 - Spotify OAuth for owner + 4 friends (as of 2026-11-04)

Builds on `01-data-sources.md` and `06-spotify-alternatives.md`; not repeated: Dev Mode cap rationale, AI ban rationale, alternatives. All claims below come from pages on developer.spotify.com fetched 2026-11-04 unless marked UNVERIFIED. Note the fetch tool summarises pages, so quotes are as returned by it and not checked against raw HTML.

## Verdict

**Feasible: YES**, for the owner (Premium) plus up to 4 allowlisted friends (cap is 5 users total, the owner counts as one if the owner also logs in; UNVERIFIED whether the owner occupies a slot). Taste signal is available via `GET /me/top/artists`, `GET /me/top/tracks` and `GET /me/following?type=artist`. Blockers are policy and quota, not API availability. The one real risk: whether using Spotify artist names for Ticketmaster matching and ranking counts as "analysis" under Developer Policy III.13 (see section 5).

## Minimal integration design

1. Create one Dev Mode app in the dashboard (section 2). Owner needs Premium or the app stops working.
2. Flow: **Authorization Code (with client secret) on the FastAPI backend**. Spotify calls it "the recommended choice" for long-running server-side apps that can keep the secret (https://developer.spotify.com/documentation/web-api/concepts/authorization). No PKCE needed because the backend is confidential. Adding PKCE on top is optional; UNVERIFIED whether Spotify accepts both together.
3. Routes: `GET /auth/spotify/login` (generate random `state`, store it in a signed httpOnly session cookie, redirect to `/authorize`), `GET /auth/spotify/callback` (compare returned `state` to the stored one and reject on mismatch, exchange the code, call `GET /me`, key the user by `account_id`), `POST /auth/spotify/disconnect` (delete tokens and all Spotify-derived data).
4. Scopes: `user-top-read` and `user-follow-read`. Nothing else for Taste. Skip playlists and recently-played at first (section 1).
5. Storage: per user, `account_id`, refresh token (encrypted at rest), cached access token + expiry. Refresh when expired.
6. Sync job on login and on a schedule: pull top artists (`long_term`, `medium_term`, `short_term`, limit 50 each) and followed artists (cursor paged, limit 50); store only artist `name`, `id`, `external_urls.spotify`, and fetch time. Do not store or use `genres`, `popularity`, `followers` (deprecated).
7. Match to Ticketmaster by normalised artist name only, in plain deterministic code. No LLM sees Spotify data.
8. UI: Spotify logo + "Listen on Spotify" link next to any Spotify-derived artist name; Disconnect button.
9. Allowlist: friends send their Spotify account email to the owner, who adds them in the dashboard (section 2). Non-allowlisted users can complete login but get 403 on API calls, so the app must handle 403 as "not on allowlist".

## 1. Endpoint availability for a new Dev Mode app

Sources: https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide, https://developer.spotify.com/documentation/web-api/references/changes/february-2026, `.../march-2026`, `.../may-2026`, `.../july-2026`, and each reference page. New Dev Mode apps got the Feb 2026 restrictions from 2026-02-11; existing apps moved on 2026-03-09. OAuth login itself is still available to new Dev Mode apps (the quota-modes page says new apps start in Dev Mode and users authenticate and are allowlisted).

| Endpoint | Status for new Dev Mode app | Notes |
|---|---|---|
| `GET /me` | Works | Fields `country`, `email`, `explicit_content`, `followers`, `product` removed (Feb 2026). `account_id` added May 2026: "public, immutable, pseudoanonymous identifier", recommended over `id` for linking accounts. Use it as the user key. |
| `GET /me/top/artists`, `/me/top/tracks` | Works, not on any removal list | Scope `user-top-read`. `time_range` = `long_term` (~1 yr), `medium_term` (~6 mo, default), `short_term` (~4 wk). `limit` default 20, max 50, plus `offset`. Reference page: https://developer.spotify.com/documentation/web-api/reference/get-users-top-artists-and-tracks |
| `GET /me/following?type=artist` | Works, not on any removal list | Scope `user-follow-read`. Cursor paging with `after`, limit max 50. Only `PUT`/`DELETE /me/following` and `/me/following/contains` were removed (replaced by `/me/library`). https://developer.spotify.com/documentation/web-api/reference/get-followed |
| `GET /me/playlists` | Works | Replacement for `GET /users/{id}/playlists`. Scopes `playlist-read-private` (+ `playlist-read-collaborative`). |
| `GET /playlists/{id}/items` | Works only for playlists the user owns or collaborates on; others return 403 | Replaces `/tracks`. Scope `playlist-read-private`. Response field `track` deprecated in favour of `item`. https://developer.spotify.com/documentation/web-api/reference/get-playlists-items |
| `GET /artists/{id}` | Works (single) | Fields `followers`, `genres`, `popularity` are marked deprecated; `followers`/`popularity` are listed as removed in the Feb changelog. The Feb changelog does NOT list `genres` as removed, and the reference sample still shows it. Whether a brand-new app actually receives non-empty `genres` is UNVERIFIED (needs a live call). |
| `GET /artists?ids=` (batch) | **Removed**, no replacement | Also removed: batch tracks, albums, shows, episodes, audiobooks, chapters, `/artists/{id}/top-tracks`, `/browse/new-releases`, `/browse/categories*`, `/markets`. One request per artist ID. |
| `GET /me/player/recently-played` | Works, not on any removal list | Scope `user-read-recently-played`; limit max 50, `after`/`before` cursors; tracks only. Optional extra signal. https://developer.spotify.com/documentation/web-api/reference/get-recently-played |
| `GET /search` | Works, smaller | Max `limit` cut from 50 to 10, default 20 to 5. |

Other changes that matter:
- Artist objects returned by top/following still carry `name`, `id`, `images`, `external_urls.spotify`, `uri`. That is enough for name matching.
- Track `external_ids` removal was reverted in March 2026; tracks lose `popularity`, `available_markets`, `linked_from`.
- Earlier (Nov 2024) removals: related artists, recommendations, audio features/analysis, per 01.
- July 2026: Client IDs per developer raised from 1 to 25; Dev Mode quota is counted per developer account, buckets shared across apps; 429 body now has `reason: "QUOTA_EXCEEDED"`. Rate limit is a rolling 30 s window; dev-mode numbers are not published (https://developer.spotify.com/documentation/web-api/concepts/rate-limits). Quota groupings "may change" (quota-modes page).
- The Feb guide says existing integrations' endpoint changes were postponed in a blog post (see 01); the endpoint lists above are what the guide states apply to Dev Mode apps. No March/May/July entry reverses the removals.

## 2. App setup

Sources: https://developer.spotify.com/documentation/web-api/concepts/quota-modes, `.../concepts/apps`, `.../tutorials/getting-started`, `.../concepts/redirect_uri`.

1. Log in to https://developer.spotify.com/dashboard as the Premium owner, accept the Developer Terms, **Create app**: name (shown on the consent screen; must not contain or resemble "Spotify", Design Guidelines), description, redirect URI(s).
2. Settings: Client ID shown; Client Secret behind "View client secret"; ROTATE button if compromised.
3. Allowlist: Dashboard -> app -> **Settings -> User Management -> Add new user**, enter name + the friend's **Spotify account email**. Limit: **5 authenticated users** in Dev Mode. Unlisted users may log in but their API calls return 403.
4. **Premium**: "The app owner must have a Spotify Premium account for apps in development mode to function"; lapse stops the app until resubscribed. Friends do not need Premium (stated requirement is on the owner only; friends' tier not addressed, UNVERIFIED).
5. "Web API" checkbox ("Which API/SDKs are you planning to use"): the getting-started and apps pages fetched do not mention it, and a web search only found old copies telling you to pick Web API. Treat as: tick Web API. Whether it is enforced is UNVERIFIED.
6. Redirect URI rules (https://developer.spotify.com/documentation/web-api/concepts/redirect_uri): exact string match (case and trailing slash); HTTPS required except loopback; loopback must be an IP literal (`http://127.0.0.1:8000/callback` or `http://[::1]:8000/callback`); **`localhost` is not allowed**; loopback IPs may vary the port. Register both `https://<prod-host>/auth/spotify/callback` and `http://127.0.0.1:8000/auth/spotify/callback`. For local dev, open the frontend via `127.0.0.1` too so the state cookie's host matches the callback host.
7. Extended Quota (unlimited users) requires a registered organisation, launched service, 250k+ MAU: not available here.

## 3. Flow, scopes, tokens

- **Authorization Code vs PKCE**: backend holds the secret, so Authorization Code. PKCE is "recommended" only where the secret cannot be stored (SPA, mobile). Do the exchange server-side only; the Next.js frontend never sees tokens. Sources: https://developer.spotify.com/documentation/web-api/tutorials/code-flow, `.../code-pkce-flow`.
- **Scopes** (https://developer.spotify.com/documentation/web-api/concepts/scopes): `user-top-read`, `user-follow-read`. Add `playlist-read-private`, `playlist-read-collaborative`, `user-read-recently-played` only if those endpoints are later used. Omitting scope gives public-only access. Request the minimum (Policy I.1).
- **State/CSRF**: `state` is optional but "strongly recommended"; compare on callback and reject mismatch. The page's own Express snippet only checks presence, so do not copy it. `show_dialog=true` forces re-consent.
- **Token exchange**: `POST https://accounts.spotify.com/api/token` with `Authorization: Basic base64(client_id:client_secret)`, `grant_type=authorization_code`, `code`, `redirect_uri`; response `access_token`, `token_type=Bearer`, `scope`, `expires_in`, `refresh_token`.
- **Refresh** (https://developer.spotify.com/documentation/web-api/tutorials/refreshing-tokens): same endpoint, `grant_type=refresh_token`. Access token lives 1 h. A new refresh token "may or may not" be returned; if absent keep the old one, if present replace it atomically. Refresh tokens last **6 months from authorisation and refreshing does not extend that**, so every user must re-consent about every 6 months. `invalid_grant` = expired/revoked: discard tokens and send the user through login again. Handle 401/403 the same way.
- **Token storage**: Spotify does not prescribe a format; the Policy requires "industry standard security protection" (I.4). Encrypt refresh tokens at rest; never log them; never ship to the browser.
- **Logout/revocation**: the authorization and apps-concept pages do not describe a token-revocation endpoint (I found none; UNVERIFIED that none exists). Users can presumably remove the app from their Spotify account page (UNVERIFIED, not on the pages fetched). The Developer Terms require you to give users "a working and easily accessible mechanism to disconnect" (V.8) and to delete their Spotify Personal Data on disconnect (section 5). So "logout" = clear the app session; "disconnect" = delete stored tokens + derived data. Handle `invalid_grant` as an implicit disconnect and run the same deletion.

## 4. spotipy vs Authlib

- **spotipy** 2.26.0, released 2026-03-03 (previous: 2.25.2 on 2025-11-26, 2.25.1 on 2025-02-27); three maintainers listed; Python >3.8; 52 open issues, 12 open PRs (https://pypi.org/project/spotipy/, https://github.com/spotipy-dev/spotipy). Changelog for 2.26.0: playlist `/tracks` endpoints renamed to `/items`, `/me/library` support, warnings for deprecated methods. It has a PKCE manager and Redis/memory cache handlers. Its `artists()` batch method calls the removed `GET /artists` endpoint, so avoid it; I did not find a spotipy release after March 2026 (the fetched releases view was empty, so UNVERIFIED for later commits). Drawbacks: synchronous `requests`-based client (blocks the asyncio loop in FastAPI unless run in a threadpool), caches tokens in a file by default (needs a custom `CacheHandler` to use the DB), and a bundled `SpotifyOAuth` built around a CLI/browser flow.
- **Authlib** 1.9.4 (page showed release date 2026-11-04, i.e. today), Python >=3.10, lists Starlette and FastAPI OAuth clients (https://pypi.org/project/Authlib/). Generic OAuth2 client: you register Spotify's authorize/token URLs and then call the Web API yourself with `httpx`. Config details (SessionMiddleware for state, `code_challenge_method`, refresh handling) not verified: the Authlib docs URLs I tried returned 404, so UNVERIFIED.
- **Recommendation**: Authlib (or plain `httpx`) for OAuth, plus ~3 small `httpx` calls to the Spotify endpoints in section 1. The API surface needed is `/me`, `/me/top/artists`, `/me/following`; that is less code than adapting spotipy's sync, file-cached auth, and it avoids spotipy methods that target removed endpoints. If you want the least code and accept blocking calls inside `run_in_threadpool`, spotipy 2.26 works for these three endpoints too. No dependency check of the repo's current `pyproject` was possible (no backend manifest found at `backend/`), so check what is already installed first (CLAUDE.md: lean on existing deps; `httpx` is likely already present, UNVERIFIED).

## 5. Developer Policy / Terms / Design Guidelines that bind this feature

Sources: https://developer.spotify.com/policy, https://developer.spotify.com/terms, https://developer.spotify.com/documentation/design.

| Item | Rule (as returned by fetch) | Effect |
|---|---|---|
| Attribution | Policy II.4.1: "clearly attribute the content as being supplied and made available by Spotify" with Spotify Marks. Design: "you must always attribute content from Spotify with the logo" for artist/album/track names, artwork, audio. | Show Spotify logo wherever Spotify-derived artist names appear (e.g. "Your Spotify top artists"). Full logo (icon + wordmark) >= 70 px; not over artwork or busy backgrounds; green only on black/white else monochrome; exclusion zone = half icon height. |
| Link back | Policy II.4.2: metadata/cover art must be accompanied by a link back to the item on Spotify. Design: labels "OPEN SPOTIFY" / "PLAY ON SPOTIFY" / "LISTEN ON SPOTIFY"; "GET SPOTIFY FREE" if not installed. | Link each displayed artist to `external_urls.spotify`. |
| Metadata display | Show names exactly as provided; truncation OK if full text reachable. Use only Spotify artwork, unaltered. | Don't rewrite displayed artist names (normalise only for matching internally). |
| App name | No "Spotify" in the name or similar-sounding; no co-branding with other brands. | "Concert Scout" is fine; do not put the Spotify logo in a lockup with Ticketmaster. |
| Deletion on revocation | Policy I.2: on disconnect or intent to stop access, "delete and no longer request or process any of that user's personal data". Terms V.8 same; Appendix A 5(c): delete Spotify Personal Data "within five (5) days". Terms V.8 requires an easily accessible disconnect mechanism. | Disconnect button; deletion job within 5 days (do it immediately); treat `invalid_grant` as disconnect. |
| Data minimisation / security | Policy I.1 request and process only what's needed; I.4 industry-standard security. | Two scopes only; encrypt refresh tokens. |
| Storing/caching content | Terms IV.3.1.1: "Do not store Spotify Content indefinitely." IV.3.2: caching only where "strictly necessary" to enhance performance; permitted: metadata, cover art. Terms II.8 defines Spotify Content as any content, data, information made available through the Platform, so artist names count. | Keep artist names only with a TTL (suggest refresh each sync, expire if not refreshed within days) and wipe on disconnect. Exact TTL is not defined by Spotify (UNVERIFIED). Do not archive history. |
| AI/ML | Policy III.14: "Do not use the Spotify Platform or any Spotify Content to train a machine learning or AI model." Terms IV.2.1.1 same, adding a bar on ingesting Spotify Content into such models. | Never put Spotify names, tracks or user taste into a Gemini/LLM prompt, embedding or fine-tune. Keep Spotify-derived data out of the LLM path entirely; deterministic code only. Whether an LLM merely seeing a ranked event list that was derived from Spotify taste is "ingesting" is not addressed (UNVERIFIED, avoid). |
| Analysis | Policy III.13: "Do not analyze the Spotify Content or the Spotify Service for any purpose" (opening of a clause that also covers building user profiles; full clause text not captured, UNVERIFIED). | Main legal risk for "Taste". Keep processing to exact-name lookups (is this top/followed artist playing nearby?), no scoring models, clustering, genre inference, or cross-user profiling. |
| Other services | Policy III.5: no product "integrated with streams or content from another service". | Aimed at streaming/playback mixing; Ticketmaster events are not streams. Low risk, still UNVERIFIED how Spotify reads it. |
| Artist sole subject | II.1: SDA must not have a specific artist as its sole subject; II.3 don't mislead about artist associated with content. | Not triggered. |

**Can top-artist names be matched to Ticketmaster artists deterministically?** Nothing on the fetched pages prohibits using a user's own artist names as a lookup key for another API. The relevant constraints are: no ML/AI use (III.14), no "analysis"/profiling (III.13), no indefinite storage (Terms IV.3.1.1), delete on disconnect. Exact or normalised string match in plain code, with names stored short-term and per-user, is the most defensible reading. This is my interpretation, not Spotify's statement; the Policy's "Spotify Content" interpretation for III.13 is the open question. Because this is a private app for 5 allowlisted users, enforcement risk is low but the compliant design above costs little.

## Open items to verify live (needs a real dashboard + token)

1. Does `GET /me/top/artists` on a brand-new app still return non-empty `genres`? (Deprecated, not listed as removed.)
2. Does the owner count toward the 5-user cap?
3. Is the "Web API" checkbox enforced?
4. Is there any token revocation endpoint, and where does a user revoke the app (account page)?
5. Do friends need Premium to authorise or only the owner?
6. Authlib/Starlette exact setup.
