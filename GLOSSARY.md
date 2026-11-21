# Concert Scout

Concert Scout finds live music a person would want to see, based on their taste and where and when they can go.

## Language

**Search**:
A single request to find concerts, defined by taste, a place, or both, with an optional date range.
_Avoid_: Query, chat, conversation, session

**Taste**:
What a person likes in music for the purpose of a Search, such as named artists or a plain description.
_Avoid_: Preferences, profile (except Taste Profile), playlist info

**Taste Profile**:
The Taste an Account keeps on every device: Artist names, favourites first, and where they came from. It never holds data from a Spotify account.
_Avoid_: Synced Taste, saved profile

**For You shelf**:
The home shelf of Concerts in the next 60 days that suit a person's Taste, matched by code from Lineup names, the closest similar Artists and Artists who share bills with them. It never calls a model.
_Avoid_: Recommendations (those are a Search's), feed

**Concert**:
A real-world live music event, as reported by its source. A festival is a Concert with a lineup.
_Avoid_: Event, show, gig

**Catalog**:
The local copy of JamBase's US Concerts that a daily sync keeps in Redis. A Search reads it and never calls JamBase.
_Avoid_: Feed, dump, mirror

**Artist**:
A performer who plays at Concerts. A Concert has one or more Artists.
_Avoid_: Attraction, act, band

**Lineup**:
The Artists performing at a Concert.
_Avoid_: Bill

**Lineup match**:
The Artists in a festival's Lineup who suit the Search, named best first. _Avoid_: score, overlap.

**Recommendation**:
Concert Scout's judgment that a Concert suits one Search, with its grade label ("You named them" for a seed Artist, "Close match" for strong, "Worth a listen" for fair; none when ungraded) and the reason why. The same Concert can have different Recommendations in different Searches.
_Avoid_: Result, suggestion, match, score

**Reading**:
What a Search was taken to mean: its Taste, place, Region and dates. The interpreter writes it, and a person can correct it.
_Avoid_: Interpretation, parse

**Region**:
A named area wider than a city and narrower than or different from a state, such as Southern California. A Search reaches it as a circle around a large city.

**Poster**:
The ranked Recommendations for one Search, seen together.
_Avoid_: Lineup, results page, list

**Ticket**:
One Recommendation seen up close, with its reason and the Concert's facts. It is not proof of purchase.
_Avoid_: Stub, card

**Saved Concert**:
A Concert a person chose to keep from a Poster.
_Avoid_: Favorite, stub, wishlist item

**Account**:
An optional Concert Scout sign-in, with Google or an email and password, that keeps a person's Saved Concerts on every device. Spotify is a separate connection, not an account.
_Avoid_: Profile, user, login

**Preview**:
Spotify's player for a Ticket's headliner, opened from Listen on the Ticket so a person can hear them before deciding.
_Avoid_: Sample, snippet, embed (in copy)

**Live clip**:
An official YouTube performance of a Ticket's headliner, opened from Watch Live on the Ticket at the moment its chapters or most liked comment point to.
_Avoid_: Video, embed (in copy), replay

**Followed Artist**:
An Artist a person with an Account chose to hear about.
_Avoid_: Subscription, favorite, tracked artist

**Alert**:
An email Concert Scout sends to an Account about something the person asked to hear about, such as a new Concert by a Followed Artist near their Alert place. An Account gets at most one a day.
_Avoid_: Notification, newsletter, digest

**Alert place**:
The one place, with a radius, where an Account wants to hear about Concerts.
_Avoid_: Home, location, area

**Sonic Card**:
The plain text Concert Scout builds about one Artist from public source facts, to turn into a vector for semantic retrieval. An Artist with too little to describe takes the average of their Co-Billed peers' vectors instead. No model writes it.
_Avoid_: Bio, description, embedding text

**Artist panel**: the side panel opened from an Artist's name on a Ticket, showing public facts from Last.fm and a link to Spotify. It never calls a model.

**Shared Poster**: a Poster kept at its own link, which anyone can open without running a Search.
_Avoid_: permalink, snapshot (an eval term)
