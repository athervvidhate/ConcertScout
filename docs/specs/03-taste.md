# Taste

Every source reduces to the same thing: a list of Artist names, favourites first. The pipeline never knows where they came from, with one exception. Data from a Spotify account has its own path.

| Source | How | Reaches the LLM |
|---|---|---|
| Typed text | Search box | Yes |
| Last.fm username | `user.getTopArtists` | Yes |
| ListenBrainz username | Top artists stats | Yes |
| Spotify Extended Streaming History | File parsed in the browser | Yes, Artist names only |
| Pasted list or CSV | Parsed in the browser | Yes |
| Spotify account | Official OAuth, allowlisted | Never |

The chosen imported Taste stays in `localStorage`, and each Search sends it. The server keeps none of it after the Search ends. A Taste typed into a Search beats the import for that Search.

Imports fetch the top 50 Artists. Only the top 5 get MusicBrainz and similar-Artist lookups. The rest match the Concert pool by name, so a long list costs no extra API calls or time.

## History file

The upload runs entirely in the browser. It sums listening time per Artist and keeps the top 50, then discards the file. Only that Artist list leaves the device.

This file is the person's own data, sent to them under privacy law. It doesn't come through the Spotify Platform, so the OAuth rules don't apply and its names can reach the LLM. That is our reading of the policy, not legal advice.

## Pasted lists

Accept one Artist per line, comma-separated text, or a CSV with an obvious Artist column. Cap the list at 100 names.

## Spotify OAuth

[ADR 0003](../adr/0003-official-spotify-access-only.md) sets the rules. Details are in [the OAuth research](../research/07-spotify-oauth.md).

- Authorization Code flow, with the client secret on FastAPI.
- Scopes: `user-top-read` and `user-follow-read`.
- Up to 5 allowlisted users. The owner needs Premium for Development Mode.
- Local redirect URI: `http://127.0.0.1:8000/auth/spotify/callback`. Spotify rejects `localhost`.
- Use Authlib with `httpx`. Do not use spotipy.
- Store tokens encrypted in Redis for seven days, keyed by an opaque `HttpOnly`, `Secure`, `SameSite=Lax` session cookie. The cookie is scoped to `/auth/spotify`, so it never accompanies `/search`. For the explicit HTTP loopback redirect in local development only, Secure is disabled; HTTPS is required elsewhere. `/auth/spotify/disconnect` deletes tokens and the cookie. A refresh preserves the original session deadline and cannot recreate a disconnected session.
- Refresh tokens expire after 6 months, so reconnecting must work without help.

## Spotify shelf

Spotify developer policy clauses III.13 and III.14 keep this data out of LLM prompts. So the shelf does not use the pipeline. Code takes the user's top Artists, normalizes names, and looks for exact matches in the Concert pool. It shows those Concerts in a separate shelf, ranked by the user's own Artist order.

The separate `/auth/spotify/shelf` route receives a place or explicit coordinates and dates. It never calls the Search pipeline. Only top Artists (up to 50) and the first 50 followed Artists are read, with top Artists first. The shelf shows at most 20 Concerts, using normalized exact Lineup names and their source facts. Its data never becomes imported Taste or enters localStorage.

The shelf has no LLM reasons. Each entry says "From your top Artists", or "An Artist you follow" when it came from the followed list. The Spotify logo and attribution follow Spotify's design rules.
