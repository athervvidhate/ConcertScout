# Accounts, Taste and Spotify: product and implementation design

November 7, 2026. Proposed implementation design. Supabase selected by the owner; application and external configuration are unchanged.

**On hold after owner feedback:** manual Artist entry is not an acceptable replacement for Spotify personalization. See [the follow-up access research](2026-11-07-spotify-public-personalization.md) before implementing these public onboarding/Taste choices. Supabase remains the selected account provider.

## Product promise

Every friend can create an account, bring their Taste, find Concerts and keep Saved Concerts across devices. Live Spotify access is an invited beta, not the prerequisite for a personal experience.

We cannot promise every friend an automatic Spotify connection today. Spotify currently limits development apps to five authenticated, allowlisted users. Someone outside that list can sometimes complete consent but gets an API refusal. Supabase does not change Spotify's access rules. Public Spotify access requires extended quota approval; the published requirements include an established organization and at least 250,000 monthly active users. This is not a practical launch dependency. [Spotify quota modes](https://developer.spotify.com/documentation/web-api/concepts/quota-modes), checked November 7, 2026.

This design builds on the [account research](2026-11-07-user-accounts.md), [Taste spec](../specs/03-taste.md), [interface spec](../specs/04-interface.md) and [Spotify boundary](../adr/0003-official-spotify-access-only.md). Where the current specs exclude accounts or promote Spotify to every visitor, these are proposed changes to make with implementation.

## Three independent things

| Thing | Purpose | Required for Search? |
|---|---|---|
| Concert Scout account | Own synced Saved Concerts and Taste | No |
| Taste | Artist names the person provides or imports | No; a place-only Search already works |
| Spotify connection | Read an invited user's Artists for the isolated shelf | No |

Google and email/password establish the same kind of Concert Scout account. Spotify is a connected service, not a sign-in method in this release. Disconnecting Spotify leaves the account, imported Taste and Saved Concerts intact.

## Navigation and entry points

Keep the current Search at the center of the home page. Do not add a mandatory welcome screen or account gate.

The existing header menu contains Saved Concerts, Your Taste and **Sign in** for guests. Signed-in visitors see **Account** instead of Sign in. Keep account actions inside the existing visual language and controls; no separate dashboard style.

On the guest Saved page, use a small, dismissible prompt: **Keep your Saved Concerts on every device.** Action: **Sign in**. After sign-in, return to the same Saved page. Opening sign-in from a Poster must preserve that Poster and active Ticket. Use an in-page dialog for sign-in; preserve a recoverable, device-local Search presentation before an external OAuth redirect. This recovery data must exclude Spotify account data and credentials.

## Sign-in and account creation

The sign-in dialog offers **Continue with Google**, then email and password. Include **Create account** and **Forgot password?**. Google uses identity scopes only. No Spotify button appears in this dialog.

- Email signup: create pending account, send verification, show **Check your email to finish creating your account** and a rate-limited resend action. Private sync starts after verification.
- Email verification and password reset callbacks have exact approved destinations. Expired or reused links explain how to request another.
- Google cancellation returns to the original page without claiming success.
- Password-reset requests use neutral confirmation so the form does not reveal whether an email has an account.
- Errors stay in the dialog. A failed sign-in never clears local Saved Concerts or Taste.

Supabase owns credentials, email verification, recovery and provider identities. Use its supported Next.js session integration rather than implement password or refresh-token handling. Public email signup requires custom SMTP and a verified sending domain. [Supabase Auth](https://supabase.com/docs/guides/auth), [email setup](https://supabase.com/docs/guides/auth/auth-smtp).

## First sign-in: preserve what already exists

Signing in must not silently assign the browser's data to a person. A shared browser may contain someone else's saves.

If there are guest Saved Concerts, offer **Add this device's Saved Concerts to your account?**, with **Add** and **Keep on this device**. Read the count from actual local data. Successful imports merge by source ID; retries cannot duplicate a save. Only mark an item imported after its server write succeeds. Preserve unsuccessful items locally and identify what could not sync.

Offer imported Taste separately. If the account already has Taste, show the existing and device sources and let the person keep the account version or replace it. Do not combine two ordered lists without a decision. Remove imported guest copies only after success and with a clear explanation that they are now in the account.

Guest data that was not imported stays in a separate device-local store. Signed-in views read only that account's data. Sign out removes account caches and restores guest mode; it must never copy the signed-in person's data back into the guest store.

## Your Taste for every friend

Replace the universal Spotify-first panel with this public order:

1. **Add Artists** — paste or enter Artist names, favourites first. Show the parsed names as removable entries before applying. Reuse the existing list parser; no new music API is needed.
2. **Import Taste** — existing Last.fm and ListenBrainz username imports; Spotify history file under this expandable section. The history file remains an advanced, asynchronous option, not a quick-connect substitute.
3. **Spotify** — a compact section explaining invited availability, or connection controls for an enabled tester.

Panel copy: **Add Artists you like. We'll use this Taste when your Search doesn't name an Artist or style.** Guests see **Saved on this device**; account holders see **Saved to your account** only after the write succeeds. Explicit Taste in a Search continues to override imported Taste.

Never make selecting Artists an intermediate step required to open a Ticket. This panel sets reusable Taste; the main Search still leads to a real Poster and Ticket.

After saving Taste, close the panel on request and offer **Find Concerts** using the main Search. Ask for a place through the existing Search/location controls. Do not assume a location from an account, IP or Google identity.

## Spotify availability and exact UI states

| State | What the visitor sees | Actions |
|---|---|---|
| Guest | **Spotify connection is available to invited testers.** | Sign in; add Artists without signing in |
| Signed in, not enabled | **Spotify connections are limited to invited testers. You can add Artists or import your Taste instead.** | Add Artists; open imports |
| Tester enabled, not connected | **Connect Spotify** with a short explanation of the separate shelf | Connect |
| Connecting | **Waiting for Spotify…** | Cancel/return; retry when no request is pending |
| Connected | **Spotify connected**, connection expiry when known | Disconnect; open shelf |
| Expired/revoked | **Reconnect Spotify to refresh your shelf.** | Reconnect; disconnect |
| Spotify refuses access | **This Spotify account isn't on the invite list. Your Concert Scout account still works.** | Add Artists; retry with the invited Spotify account |
| Service unavailable | **Spotify couldn't connect. Try again later.** | Retry; use other Taste |

No disabled giant green button for the public, no promise of a future invite, and no request queue that suggests capacity we do not have. Keep Spotify attribution where its data appears.

The owner manages Spotify's actual allowlist in its developer dashboard and enables the corresponding Concert Scout account through an operator-only configuration/script. No admin UI is needed. Enabling a Concert Scout account does not itself allowlist a Spotify account. Google and Spotify emails need not match; actual Spotify authorization proves connection ownership. Never infer eligibility from Google email or expose other testers' identities or remaining slots.

The server enforces the tester flag when starting authorization; hiding a button is insufficient. A Spotify 403 remains a normal recoverable state even for an enabled tester. Existing connected guests must sign in and reconnect before they can use an account-owned connection. End the guest OAuth storage path as part of that migration rather than maintain two permanent systems.

## Personalized Concerts: honest differences

With user-provided/imported Taste, the existing Search pipeline makes Recommendations and reasons. With connected Spotify, the existing shelf uses exact Artist-name matching and source Concert facts, independently of the models. These are two useful experiences, but must not be described as equivalent automatic Spotify personalization.

The shelf stays clearly labeled and does not silently replace imported Taste. Empty shelf: **No Concerts by your Spotify Artists here in these dates.** Offer changing the place/dates or using the main Search. Do not label zero matches as a broken connection.

Saved Concerts from the shelf can sync as source-backed Concerts. Do not attach the listening history, Spotify Artist ranking or a Spotify-derived explanation to their synced records. Spotify account data never becomes imported Taste, Search input, report content or model telemetry. Raw history-file parsing remains in the browser under the existing documented policy interpretation; only explicitly imported Artist names may sync, never the file.

## Account page

Keep this small: **Sign-in methods**, **Your Taste**, **Connections**, **Sign out**, **Delete account**. Saved Concerts retain their existing page.

Additional Google identities require proof through the provider. Password addition/recovery requires Supabase's verified flow. Prevent removal of the last usable sign-in method. Let Supabase handle its documented verified-email linking; do not implement email-based account merging. [Identity linking](https://supabase.com/docs/guides/auth/auth-identity-linking).

Deleting an account requires explicit confirmation and recent authentication. Disable private access first, cancel pending connections, delete encrypted Spotify credentials/cache and application rows, then remove the Auth identity. Cleanup failures leave the account inaccessible and deletion retryable, rather than leave active orphan credentials. Explain that deleting an account does not erase guest saves stored separately on this device; offer a separate local-data action.

## Data ownership and service boundaries

Supabase Auth owns identity; its user ID is the ownership key. Supabase Postgres stores durable data. FastAPI owns application reads/writes, source validation and Spotify. Redis retains its current cache, budget and encrypted Spotify roles.

| Record | Minimum fields / behavior |
|---|---|
| Account settings | User ID, Spotify tester flag; flag writable only by the operator |
| Saved Concert | User ID, source, source Concert ID, saved timestamp, server-validated Concert snapshot; unique per user/source/ID |
| Imported Taste | User ID, existing source kind, ordered Artist names, revision; one current list per user |
| Spotify credentials/cache | Encrypted, account-owned Redis entries; credential retention remains seven days, Artist cache one day |
| Pending authorization | One-use state, user ID, browser binding, approved return destination, short expiry; no credentials in URLs |

Saved Concerts are Concerts, not permanent Recommendations for every future Search. The account list can show source facts without synthesizing a reason. Guest-import metadata is untrusted: validate IDs and recover facts from Ticketmaster or a trusted server source cache. Unavailable records stay local with an import warning, not silently disappear or become verified facts.

Private endpoints use the authenticated subject; no caller-selected owner ID. Enable row policies for every account-owned table. Use the user's verified token for database access so row policies apply, and keep any privileged maintenance key out of normal browser requests. The tester flag cannot be changed through account-settings updates.

Next.js obtains/refreshes the Supabase session through its supported library. Browser calls to FastAPI attach the short-lived application access token in Authorization; Spotify tokens never follow this path. FastAPI validates signature, issuer, audience and expiry with asymmetric signing keys and a cached JWKS verifier, including rotation. Restrict credentialed origins and redirects to exact configured destinations. Existing IP, bot and global spend limits remain; changing accounts cannot reset a visitor's IP budget. [JWT verification](https://supabase.com/docs/guides/auth/jwts).

Proposed private operations: read account state; list/save/remove Saved Concerts; read/replace/delete imported Taste; start/confirm/disconnect Spotify; request account deletion. Save is idempotent by source ID, removal is idempotent, and Taste replacement includes an expected revision so a stale device cannot silently overwrite a newer list. Failed writes retain a visible unsynced state; do not add an offline write queue in the first slice.

## Secure account-owned Spotify authorization

The current OAuth callback receives a cookie, not the application's bearer token. Do not assume the callback still belongs to whoever started signing in.

1. An authenticated start request checks tester access, records user-bound, expiring state and sets a browser-binding HttpOnly cookie. It returns the approved Spotify authorization destination.
2. Spotify redirects to FastAPI. Validate matching cookie/state and consume state once. Exchange the code and check access through the existing adapter. Keep credentials in a short-lived encrypted pending entry; do not install the account connection yet.
3. Return to the frontend with an opaque completion handle. The frontend sends an authenticated confirmation request. Require the same user, browser binding, unconsumed handle, live account and tester access. Switching accounts, signing out or deleting the account prevents attachment.
4. Install the encrypted account-owned connection atomically, delete the pending entry and strip the handle from navigation history. Cancellation/timeout clears pending entries. No Spotify code or token enters frontend storage, logs or the page URL beyond Spotify's necessary server callback.

Serialize refresh per account and use a connection generation/version when persisting rotated tokens. Disconnect invalidates that generation before deleting credentials and cache, so in-flight refreshes cannot restore it. Signing out hides the shelf; disconnecting removes the connection for every device. Connection expiry does not delete the Concert Scout account.

## Implementation slices and Done when

**1. Accounts and synced Saved Concerts.** Configure Supabase, Google and SMTP; add auth/session verification, row policies, Saved Concert operations, guest import and account deletion. Update overview/product/platform/privacy specs and record the provider ADR. Done when two accounts cannot access each other's data, saves persist on a second browser, guest import safely retries, verification/recovery work, and sign-out/account switching clears private UI. Search must still work for guests and during an auth outage.

**2. Synced Taste and public panel.** Reorder Your Taste around Artist lists and existing imports; add explicit guest migration and revision conflicts. Done when Taste follows an account across browsers, explicit Search Taste wins, failed writes are visible, raw history files stay local, and no account's Taste appears for another.

**3. Account-owned Spotify beta.** Add operator eligibility, bound authorization, encrypted ownership, refresh serialization and cross-device disconnect. Remove guest OAuth ownership. Done when enabled testers can connect from one browser and use the shelf in another; disabled users cannot start; 403/cancellation/expiry recover; account-switch callbacks fail; disconnect/deletion cannot be undone by in-flight refresh; Spotify data never reaches models or general Taste storage.

Use [the repo's test boundaries](../development/testing.md): contract tests for ownership and lifecycle behavior, browser journeys at 390/1280 with keyboard and reduced motion, and separate real-provider acceptance for Google/email/Spotify. Include two real invited Spotify accounts to verify isolation. No live provider success may be claimed from substitutes. Leave the local app running after implementation; do not deploy as part of design work.

## Launch configuration

Owner-selected Supabase is the provider decision. Start on Free only with the documented inactivity-pausing tradeoff; its paid plan currently starts at $25/month, exceeding the existing total app budget. This design does not authorize a paid subscription. Require exact local/production callback URLs, a verified SMTP sender, asymmetric signing keys and a tested deletion procedure before public registration. [Supabase pricing](https://supabase.com/pricing).

This document changes no production code, accounts, provider settings or deployments. Visual polish should use the current approved UI or the separately selected redesign; the flows above do not require choosing a new visual direction.
