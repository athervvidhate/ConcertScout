# Spotify connection setup and boundaries

Issue #29 adds the official Authorization Code flow and a separate deterministic shelf. Ordinary Searches and every other Taste import still work with Spotify disabled.

## Configuration

The local API reads the ignored `api/.env`:

- `SPOTIFY_CLIENT_ID`: the app's client ID.
- `SPOTIFY_CLIENT_SECRET`: the server-held client secret.
- `SPOTIFY_ENCRYPTION_KEY`: a Fernet key. A private local key has been generated in the active worktree's ignored file; do not commit, print or rotate it casually. Another installation can generate its own key with the command in `.env.example`.
- `SPOTIFY_REDIRECT_URI`: `http://127.0.0.1:8000/auth/spotify/callback` locally. Use the exact registered HTTPS callback in production.

Create/configure the app in the [Spotify developer dashboard](https://developer.spotify.com/dashboard), register the callback, and add the owner/friends to its development allowlist. Use the frontend at `http://127.0.0.1:3000`, not localhost, so browser cookies share a site with the loopback API. The owner still has to supply the app credentials and complete a real consent flow; this has not been done here. Enter secrets privately, never in an issue or PR.

The connection link lives inside Your Taste and opens a new tab, preserving an existing Poster. The original tab refreshes its connection status when focused. Imported Taste and a connected Spotify account are separate controls.

## Data flow

1. The server creates a random state, stores its hash for ten minutes in Redis, and binds it to an HttpOnly cookie.
2. The callback checks the browser cookie and consumes state once before exchanging the code with Authlib. It permits return redirects only to exact CORS allowlist origins.
3. Tokens are encrypted with Fernet in Redis under a hash of a random session ID, expiring after seven days. No account identifier or Artist list is stored. Refresh preserves the original expiry and cannot resurrect a session deleted by Disconnect.
4. An opaque HttpOnly, SameSite=Lax cookie is scoped to `/auth/spotify`, so it is not sent to `/search`. It is Secure with HTTPS; the explicit HTTP loopback development setup is the sole exception. HTTPS is required elsewhere.
5. The shelf reads up to 50 top Artists, then up to 50 followed Artists, preserving top-Artist order. It uses normalized exact Lineup names against the source Concert pool and shows at most 20 Concerts. There are no model reasons or calls to the Search pipeline.
6. Disconnect deletes the encrypted Redis entry and browser cookie. Invalid/expired credentials are removed. Spotify responses have `private, no-store`; callback query parameters are stripped from Uvicorn's access-log scope after route processing.

Artist names and links are displayed as Spotify supplied them, beside its official unmodified logo, with links back to Spotify. Concert facts and Ticket links come from Ticketmaster. A followed-only Artist is labeled as followed rather than falsely described as a top Artist. Account data never enters imported Taste, localStorage, or model requests.

Authlib 1.9.5 uses HTTPX2 internally for OAuth. The adapter confines its incomplete library typing; the rest of the app uses typed credentials and Artist models. Other source calls continue using the existing async HTTP client. There is no unofficial client, password or session-cookie authentication.

## Evidence and pending acceptance

Run `make check` for API/privacy/session contracts, and `make e2e` for browser journeys. The test server substitutes the typed Spotify adapter while using real OAuth routes, API/pipeline, encryption, cookies and isolated real Redis. It never invents Spotify API JSON or pretends to authenticate a real account.

Verified contracts include state binding/replay refusal, encryption/TTL, deletion, no model access, source-fact preservation, denied access messaging, origin guards, secure production cookies, invalid configuration redaction, and a concurrent refresh failing to resurrect a disconnected session. Browser checks cover the separate attributed shelf, cookie scope, no Spotify Taste in Search, disconnect and access denial at 1280px/390px.

Live token exchange, refresh, allowlist response and the configured production cookie/site relationship remain pending owner credentials and a real account. Keep the PR draft until those integration checks are complete. This document does not assert that all Spotify catalog data is available or that an untested deployment works.

Primary references: [Spotify Authorization Code](https://developer.spotify.com/documentation/web-api/tutorials/code-flow), [redirect URIs](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri), [top items](https://developer.spotify.com/documentation/web-api/reference/get-users-top-artists-and-tracks), [followed Artists](https://developer.spotify.com/documentation/web-api/reference/get-followed), [branding](https://developer.spotify.com/documentation/design), and [Authlib's async client](https://docs.authlib.org/en/stable/oauth2/client/http/httpx.html).
