# User accounts and connected services

Research, November 7, 2026. The owner subsequently selected Supabase. The [account experience design](2026-11-07-account-experience-design.md) is the implementation proposal, including public Spotify availability and migration decisions. No implementation or provider configuration has occurred.

## Recommendation

Add optional Concert Scout accounts with Google and email/password sign-in, using Supabase Auth and Postgres. Keep Spotify as an independently connected service. The first useful account feature is syncing Saved Concerts across devices, followed by imported Taste. Searching and saving locally remain available to guests.

An account identifies a person in Concert Scout. A connection grants access to another service. Connecting Spotify must not be required to create an account, and disconnecting it must not delete the account or prevent sign-in.

## What exists today

- [Overview](../specs/00-overview.md) explicitly excludes accounts. This proposal is a new slice, not an unfinished requirement of the rebuild.
- [Saved Concerts](../../frontend/lib/saved.ts) stores Recommendations and skipped source IDs in localStorage. [Imported Taste](../../frontend/lib/taste.ts) is also device-local.
- [Spotify routes](../../api/concert_scout/spotify.py) store encrypted credentials in Redis for seven days behind a device cookie. OAuth state currently records a return origin, not a Concert Scout user. Spotify therefore connects a browser; it does not create an application account.
- The [Spotify shelf](../specs/03-taste.md) stays separate from Search. Account work must preserve [ADR 0003](../adr/0003-official-spotify-access-only.md): no Spotify account data reaches models.
- The inspected checkout is `development`, head `967d4d8`. Unrelated UI studies are present and remain untouched.

## Provider choice

| Option | Fit | Tradeoff |
|---|---|---|
| Supabase Auth + Postgres | Recommended: identity and durable account data in one service | Email delivery setup and free-project inactivity pausing |
| Clerk + a durable database | Strong alternative when ready-made account screens are the priority | Another service is still needed for Saved Concerts and Taste |
| Build password authentication in FastAPI | Most direct control | Adds password storage, recovery, verification and session lifecycle work to this portfolio project |

Supabase supports passwords, email links/codes, Google, and Spotify, with JWT authentication and database row policies. This covers the requested sign-in methods without building credential handling ourselves. [Auth documentation](https://supabase.com/docs/guides/auth).

Supabase Free currently includes 50,000 monthly active users and a 500 MB database, but projects pause after a week of inactivity. Pro starts at $25/month, above the existing $10–15 total monthly budget. Free is a reasonable trial; an always-available account service at the current budget remains an operational decision. Do not assume free includes production backups. [Pricing](https://supabase.com/pricing).

Clerk currently offers a free Hobby plan with prebuilt sign-in and account screens. Its integration documentation illustrates the separate database and row policies still required for application data. This is viable, but Supabase alone fits this app's combined authentication and persistence need more simply. That preference is an architectural judgment. [Clerk pricing](https://clerk.com/pricing), [database integration](https://clerk.com/docs/guides/development/integrations/databases/supabase).

## Proposed experience

1. Visitors can Search and Save immediately. Explain that guest saves stay on this device.
2. Offer **Sign in to sync your Saved Concerts** from the menu and Saved page.
3. Sign-in offers **Continue with Google** and email/password, including email verification and password reset. Email codes are an available alternative if we later prefer passwordless sign-in.
4. After sign-in, offer **Add this device's Saved Concerts to your account**. Merge by source ID and make repeated imports safe. Ask separately before syncing device-local imported Taste; shared-device data must not silently become another user's data.
5. Account settings show sign-in methods, connected services, sign out and account deletion. Spotify appears here and in Your Taste as **Connect Spotify**.
6. Signing out clears account-specific data from the visible UI and client caches. Guest data and unsynced saves must not be lost or accidentally exposed to the next account.

Google sign-in needs identity scopes only; it does not need Gmail, Drive or Calendar access. Other sign-in providers can be added later when there is a concrete need.

## Spotify: connection first, sign-in later

Spotify's current development mode permits five authenticated, allowlisted users and requires the app owner to have Premium. Unallowlisted users may complete login but their API requests return 403. Extended access has organization and scale requirements unsuitable for this portfolio app today. Accounts do not remove these limits. [Spotify quota modes](https://developer.spotify.com/documentation/web-api/concepts/quota-modes).

Supabase does support Spotify sign-in technically. Defer presenting it as a public sign-in option because our Spotify access is restricted and it would couple account access to an optional music integration. Google/email remain available to everyone. [Spotify auth integration](https://supabase.com/docs/guides/auth/social-login/auth-spotify).

Preserve the existing FastAPI OAuth adapter and isolated shelf, but make signed-in connections belong to the account:

- Bind one-use OAuth state to the authenticated user, browser and allowed return destination. Reject callbacks after an account switch or logout. Never accept an arbitrary user ID from the browser.
- Let a connection established on one device serve the same authenticated account on another device. Keep credentials encrypted on the server; never put Spotify tokens in localStorage, general profile fields, analytics or model input.
- Keep the existing seven-day credential retention and one-day Artist cache initially. An account persists after that deadline; the UI asks to reconnect Spotify when needed. Longer retention is a separate explicit policy change.
- Disconnect deletes credentials and the Artist cache across devices. Refresh and disconnect must be atomic enough that an in-flight refresh cannot restore deleted credentials; concurrent refreshes must not overwrite rotated tokens.
- Existing guest Spotify connections need a fresh account-bound authorization before attachment. Do not infer ownership from an email address or silently claim a shared browser's connection.
- Guest Spotify behavior can remain during rollout, with a clear device-only label. The new account-bound flow replaces that storage path when the product migrates fully; do not accumulate permanent compatibility code.

## Application boundaries

Supabase handles identities and credentials. Postgres holds account-owned Saved Concerts and, in the next slice, imported Taste with its source. Redis remains an expiring cache and credential store, not the durable account database.

Next.js handles sign-in, callback and account UI. FastAPI verifies the application's access token before private operations and derives ownership from its verified subject. With asymmetric Supabase signing keys, use the published JWKS and a maintained verifier; validate signature, issuer, audience and expiry, including key rotation. Decoding a JWT is not verification. [JWT documentation](https://supabase.com/docs/guides/auth/jwts).

Enable row-level policies on every account-owned table. Keep privileged database keys server-only; any server path that bypasses those policies needs explicit ownership checks. Saved Concert facts remain source-backed; browser-submitted Concert metadata is not an authoritative source record. Keep the existing global spend, bot and IP protections; accounts must not provide a way around limits.

Use a stable internal user ID, not an email, as the ownership key. Supabase documents automatic linking for matching verified email identities and explicit linking for additional identities. Test those actual rules rather than adding our own email-based merge. Require authenticated provider proof for explicit linking, and prevent removal of the last usable sign-in method. [Identity linking](https://supabase.com/docs/guides/auth/auth-identity-linking).

Email sign-up requires a real mail setup. Supabase's default mail service is restricted to project-team addresses, currently limited to two messages/hour and intended for testing. Configure custom SMTP, for example through Resend, with a verified sending domain before opening registration. [SMTP documentation](https://supabase.com/docs/guides/auth/auth-smtp).

## Delivery slices and acceptance

1. **Accounts + Saved Concerts:** Google and verified email/password, reset, sign out, deletion, durable saves, explicit guest import. Update the overview, product, platform and privacy text and record the provider decision in an ADR.
2. **Account-owned Spotify:** OAuth ownership, cross-device shelf, expiry/reconnect, disconnect, refresh-race protection and account-deletion cleanup. Update Taste and privacy retention rules.
3. **Synced imported Taste:** explicit import, source provenance, predictable concurrent updates. Spotify account data remains outside this field and outside Search.
4. **Additional sign-in methods:** only after testing identity linking, different provider emails, cancellation and recovery. Spotify sign-in remains subject to its access restrictions.

Follow [testing contracts](../development/testing.md). Prove that account A cannot read, edit or delete account B's data; invalid/expired/wrong-project tokens fail; imports are idempotent; logout/account switching cannot display old private data; callback state cannot attach a connection to another account; refresh cannot undo disconnect; Spotify data never enters Search/model traces. Exercise real managed-provider Google/email flows in a separate test project, including verification and password recovery. Local substitutes do not establish provider compatibility.

Setup prerequisites: a Supabase project and signing-key configuration, Google OAuth client and exact callback allowlists, verified SMTP sender, account-deletion behavior, and a decision about free-tier pausing. No external projects, credentials, deployments or production changes were made for this proposal.
