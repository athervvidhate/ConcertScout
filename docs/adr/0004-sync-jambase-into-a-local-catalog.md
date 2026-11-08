# Sync JamBase into a local Catalog

JamBase is read from a Catalog in Redis that a daily scheduled job keeps current, never from a Search. Calling JamBase per Search would let visitors spend a 1,000-call monthly plan whose overage bills rather than stops, and would add a network wait to every Search. JamBase documents this pattern: download once, then ask only for records changed since the last run. The Catalog covers the US for 90 days, because the whole world's daily changes would not fit the plan, and Ticketmaster already covers tours further out.

The Developer plan does not return MusicBrainz IDs, so the same job resolves Catalog Artists by exact name through MusicBrainz, leaving ties unresolved rather than guessing.
