# Alerts by email through Resend

A person with an Account can follow Artists and hear by email when one of them has a Concert near a place they choose. Email reaches people who are not looking at the app, which is the whole point, and it needs no app install or push permission. Browser push would reach only a device that granted it, and SMS costs money per message.

Resend sends the mail. The `concertscout.app` domain is already verified there for sign-in mail, the API already has a small Resend adapter for feedback reports, and the free plan costs nothing. Its limits shape the design: 100 emails a day and 3,000 a month, shared with sign-in mail. So an Account gets at most one Alert a day, holding everything new for it, and the daily run stops well short of the daily limit so confirmation and recovery emails still go out. An Account that does not fit in a day's run waits for the next one; nothing is dropped.

Alerts run as their own daily scheduled job, an hour after the Catalog sync, rather than inside it. The sync already spends its whole time budget behind its own lock. The job builds one Concert pool per distinct Alert place with the same code a Search uses, Ticketmaster and the JamBase Catalog, and matches Lineup names to Followed Artists in code. No model is called, and every fact in an Alert comes from the source record (ADR 0002).

Followed Artists, the Alert place and the record of what each Account was told live in Supabase beside Saved Concerts, under the same rules as ADR 0004: the browser reads and removes its own rows, and the API writes them. Deleting the Account deletes them all. A Concert is recorded as sent only after Resend accepts the email, and each send carries an idempotency key for that Account and day, so a retried run neither loses nor repeats a Concert.

Every Alert carries a signed one-click unsubscribe link and the matching `List-Unsubscribe` headers, which work without signing in. Followed Artists never come from a Spotify connection, because ADR 0003 keeps that data out of general Taste storage.
