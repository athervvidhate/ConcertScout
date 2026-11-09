# SpotAPI local read-only spike

November 7, 2026. The owner authorized a local unofficial-client experiment. Production still uses official Spotify OAuth; this experiment does not change ADR 0003 or enable unofficial access for visitors.

## Setup and provenance

- Wrapper: [carlelieser/spot-api](https://github.com/carlelieser/spot-api), commit `2a2a99e3e7b4c18096d45ae14a483741533d822d`.
- Temporary clone and Python 3.12 environment: `/private/tmp/concert-scout-spotapi-wrapper`.
- Wrapper requirements pin SpotAPI `1.2.8`, FastAPI `0.115.6`, Uvicorn `0.34.0` and Pydantic `2.10.4`. Added HTTPX `0.28.1` only to this isolated environment for in-process HTTP testing. Installed dependency versions are recorded in its `installed-requirements.txt`.
- Probe: `/private/tmp/concert-scout-spotapi-wrapper/probe.py`. It exercises the actual wrapper FastAPI routes using Starlette's TestClient. No public HTTP service or third-party hosted proxy is used.
- No Concert Scout dependency, application, provider, allowlist or deployment changes. No passwords requested, CAPTCHA solver configured, account writes attempted or paid service subscribed.

## Source findings

The wrapper supports cookie-based account verification, Liked Song pages and library entries. `Login.from_cookies` accepts the Spotify web session cookie `sp_dc`; an arbitrary local identifier is sufficient because the account is resolved upstream. This bypasses the application's developer-client OAuth flow, not the need for an authenticated Spotify account.

The pinned SpotAPI source has a concrete multi-user isolation problem: `Config.client` is a dataclass field with `default=TLSClient(...)`, not a fresh client factory. The wrapper uses this shared default, and `from_cookies` clears/replaces the client's cookie jar. Separate requests can therefore overwrite the same transport's session state. The experiment explicitly supplies a fresh transport per account. Do not deploy the unmodified wrapper for multiple friends.

The wrapper returns exception strings in HTTP errors; FastAPI's default validation error can include rejected input. The test harness replaces both with generic errors. Source methods for modifying playlists/account data exist in the dependency, but the probe does not invoke them.

SpotAPI obtains current public handshake metadata from `code.thetadev.de`, separately from Spotify API calls. The probe restricts that dependency request to its exact URL without cookies or Authorization. Spotify traffic is restricted to Spotify/CDN hosts. The harness permits only the specific library/public-playlist-read GraphQL operations and client-token POST, disables environment proxies and redirects, uses no automatic transport retries, caps calls at 200 for the complete private-read sequence, and sets a ten-second timeout per Spotify request. Live runs are supervised with a 90-second whole-process deadline. The budget accounts for each new wrapper session rediscovering Spotify's query hashes.

## Verification so far

`probe.py --self-test` passes six local boundary checks without any external calls:

1. Distinct account transports.
2. Distinct cookie jars after constructing two sessions.
3. HTTP health route.
4. API-key refusal.
5. Secret redaction from request-validation errors.
6. Secret redaction from unexpected upstream errors.

These prove probe isolation and output behavior, not compatibility with live Spotify. No vendor JSON is fabricated in these checks.

## Actual public-playlist test

The public playlist ID `3cEYpjA9oz9GiPac4AsH4n`, used as an example in Spotify's playlist documentation, returned **five real track rows and seven distinct source-provided Artist names**. The final extraction run took **5.37 seconds** and required no Spotify session cookie or developer app. No names or playlist payload were printed or persisted. Artist extraction follows the returned `artists.items[].profile.name` fields; an initial extractor relying only on `__typename: Artist` returned zero and was corrected against the real structure.

One cold read made **80 HTTP requests**: two to `open.spotify.com`, 76 to `open.spotifycdn.com`, one client-token request and one GraphQL read. All returned 200. The public dependency lookup is additional. This JavaScript-discovery overhead is material before considering concurrent friends, function cold starts or deployment. No optimization or cache was added during this experiment.

An earlier request for playlist `37i9dQZF1DXcBWIGoYBM5` returned a GraphQL union with `__typename` and `message`, but no content/tracks, despite HTTP 200 and no top-level GraphQL errors. The initial generic data-present check incorrectly called that successful; strict payload validation caught it. Do not infer universal public-playlist access or diagnose the precise refusal reason from this evidence. The final probe treats a union without content as refused.

The result establishes a concrete no-paid-scraper public-playlist path for this sample. It does not establish anonymous access to every playlist, private Liked Songs or top-Artist listening rankings.

## Live acceptance

The first live run requires an owner-supplied session cookie via the private secret-entry tool. Never paste it into chat, command arguments, source, reports or the checkpoint. Read it from the tool's private file inside the probe. The temporary input file is a credential; no library response or Artist/track names should be written to disk or model context.

Run verification first, then at most ten Liked Songs and ten library entries. Stop at the first failure. Report only HTTP status, duration, whether identity/data resolved, and item counts. Retain no account/library payload. On 403/429, stop instead of cycling identities or proxies. Authentication challenges require the person to complete normal Spotify sign-in; do not automate challenges.

## Actual authenticated test

After the owner asked for entry instructions, a third private-entry card received a session. The supervised probe completed the following in one run:

| Read | Observed result | Duration |
|---|---|---|
| `/verify` | HTTP 200; account identity resolved, identifier not printed | 0.27s |
| `/library/tracks?limit=10&offset=0` | HTTP 200; ten real Liked Song rows, with pagination indicating more | 4.82s |
| `/library/playlists?limit=10` | HTTP 200; data object present, no top-level GraphQL errors | 3.99s |

The tracks check validates the wrapper's actual `items` and `total` fields. The library check is weaker: it does not validate the nested entry union or count its rows. Given the public-playlist union finding above, do not call this proven playlist enumeration. No Artist extraction or Concert matching was attempted on the private response.

No Concert Scout Spotify client ID/secret, OAuth allowlist, paid API, external hosted proxy or account-write endpoint was used. The only supplied account credential was the owner-entered browser cookie. The probe retained no raw account/library response, names or session dump. Its supervisor deleted the single-use credential file after the process exited; deletion was checked separately.

The complete sequence made 161 Spotify/CDN calls: one profile read, four player requests, 152 JavaScript requests, two client-token calls and two GraphQL reads. This overhead comes from recreating each wrapper session and needs investigation before hosting. The two library-read route times sum to 8.81s; this is one local run, not a latency distribution or a Vercel benchmark.

This establishes a working cookie-authenticated private Liked Song read for one account with these pinned versions. It does not prove access for a second account, expiry/reconnect, top-Artists availability, phone onboarding, hosting compatibility or production suitability. The wrapper exposes library membership; it does not establish listening-frequency rankings. The upstream shared-client bug must remain fixed in any further experiment.

Next meaningful step: validate an isolated Artist extractor inside the local process, then source-backed Concert matching through the deterministic shelf. For a real multi-user product, separately resolve how users grant access without manually copying browser cookies, account/session isolation, revocation/expiry and the official-only ADR conflict. Do not interpret successful testing as authorization to deploy or change the production login flow.
