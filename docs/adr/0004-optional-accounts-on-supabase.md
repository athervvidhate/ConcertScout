# Optional accounts on Supabase

People can create an optional Concert Scout account with Google or an email and password, so their Saved Concerts follow them to every device. Supabase provides both the sign-in service and the Postgres database, so passwords, email verification, recovery and identity linking are not built here. Clerk would need a second service for the data, and our own password handling would add risk to a portfolio app for no gain.

The browser holds the Supabase session. FastAPI checks each access token against the project's published signing keys, and the token's subject is the only owner it acts for. Reads and removals go to the database with the person's own token, so row-level security decides what they reach. Writes use the server's secret key, because the API reads a saved Concert's facts from Ticketmaster rather than trusting facts the browser sends (ADR 0002). The browser role has no insert or update grant at all.

Accounts never gate Search, and guests still save on their device. Spotify remains a separate, device-bound connection (ADR 0003). Making it belong to an account is its own issue.

Supabase's free plan pauses a project after a week without activity, and its paid plan costs more than this app's whole monthly budget. A paused project stops sign-in and synced saves, not Search.
