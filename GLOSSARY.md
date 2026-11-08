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

**Artist**:
A performer who plays at Concerts. A Concert has one or more Artists.
_Avoid_: Attraction, act, band

**Lineup**:
The Artists performing at a Concert.
_Avoid_: Bill

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

**Artist panel**: the side panel opened from an Artist's name on a Ticket, showing public facts from Last.fm and a link to Spotify. It never calls a model.
