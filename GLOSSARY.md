# Concert Scout

Concert Scout finds live music a person would want to see, based on their taste and where and when they can go.

## Language

**Search**:
A single request to find concerts, defined by taste, a place, or both, with an optional date range.
_Avoid_: Query, chat, conversation, session

**Taste**:
What a person likes in music for the purpose of a Search, such as named artists or a plain description.
_Avoid_: Preferences, profile, playlist info

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
Concert Scout's judgment that a Concert suits one Search, with the reason why. The same Concert can have different Recommendations in different Searches.
_Avoid_: Result, suggestion, match

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

**Followed Artist**:
An Artist a person with an Account chose to hear about.
_Avoid_: Subscription, favorite, tracked artist

**Alert**:
An email Concert Scout sends to an Account about something the person asked to hear about, such as a new Concert by a Followed Artist near their Alert place. An Account gets at most one a day.
_Avoid_: Notification, newsletter, digest

**Alert place**:
The one place, with a radius, where an Account wants to hear about Concerts.
_Avoid_: Home, location, area

**Artist panel**: the side panel opened from an Artist's name on a Ticket, showing public facts from Last.fm and a link to Spotify. It never calls a model.

**Shared Poster**: a Poster kept at its own link, which anyone can open without running a Search.
_Avoid_: permalink, snapshot (an eval term)
