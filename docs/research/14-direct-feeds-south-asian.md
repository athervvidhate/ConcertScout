# Direct feeds for South Asian Concerts

Researched November 7, 2026, after the national JamBase Catalog (#73, #78). The question: which permitted, machine-readable source would add the Bollywood, Punjabi, Hindi and ghazal Concerts that Southern California families attend and that neither Ticketmaster nor JamBase lists. No accounts were created and no outreach was sent.

## What the current sources miss

The local JamBase Catalog holds every California event for the next 90 days (14,081 US events across nine states, all of California included). A keyword scan of its California listings found exactly two South Asian Concerts: Sid Sriram at Blue Note Los Angeles and Jubin Nautiyal at San Jose Civic. The other ten keyword hits were false positives ("Holidays", "Pietragallo").

Sulekha's Los Angeles metro page, read the same day, listed Concerts and music nights that appear in neither source, for example:

| Listing | Date | Venue | Kind |
|---|---|---|---|
| Geeton Ka Safar Live | Nov 22, 6 PM | Valencia High School Auditorium, Placentia | live Hindi film songs, Artists unnamed |
| MHJ Live Season 3 | Nov 15, 4:30 PM | John F. Kennedy High School, La Palma | live show |
| Dur E Fishan Meet & Greet and Musical Night | Dec 6, 8 PM | Luxor Banquet Hall, Buena Park | musical night with a named actor |
| L.A. Thumakda | Nov 28, 9 PM | Sunset Rooftop, Los Angeles | Bollywood DJ night |
| San Diego Sabki Bajate Raho | Nov 27, 9 PM | Ambiance Lounge, San Diego | DJ night |
| Theherav, The Ghazal Project | Dec 11 and 12 | Starbright Theater, Campbell | ghazal Concert (Bay Area) |
| Udit Narayan and Aditya Narayan, LEGACY | Dec 5 | Center for the Performing Arts, San Jose | major Artists (Bay Area) |
| Ustad Ghulam Ali, Aamir Ghulam Ali, Jaspinder Narula | Mar 13 | Center for the Performing Arts, San Jose | ghazal and Sufi (Bay Area) |

The same page mixes in galas, a wedding expo, comedy, a membership drive, workshops and Phoenix events. A source of this kind needs category filtering and venue-location filtering before anything reaches a Poster.

So the gap is the community circuit: school auditoriums, banquet halls and lounges, run by a handful of promoters (Bollywood In Hollywood, Radio5, Tisha Entertainment, Our Indian Culture and others) who sell through Sulekha, Eventbrite and sometimes AXS.

## Sources checked

| Source | Access | Verdict |
|---|---|---|
| **Sulekha Events** | `robots.txt` allows every agent, but the [Terms](https://us.sulekha.com/terms) forbid using "robots, scrapers, spiders … to monitor, copy" the site, "data mining, data scraping, data harvesting", and compiling "a collection, compilation, database or directory". No API, RSS or iCal link. Event pages carry schema.org `Event` JSON-LD with name, start, location, organizer, offers and image, but no `performer` and no `eventStatus`, and November times carry `-07:00` where California is on `-08:00`. | Best coverage of the circuit, but no scraping. Ask for a feed (draft below). A feed would still need times corrected from the venue location, and Artists only where named. |
| **Eventbrite** | The broad search endpoint was shut down in 2019. The [API reference](https://www.eventbrite.com/platform/api) documents "List Events by Venue ID" with `only_public`, and events by organization. The API Terms (read through a cached copy, because the current page answered 403) require showing the event title and a direct link to its Eventbrite page, and forbid storing data about past events without the organizer's permission. Authentication and rate limits were not readable without an account. | Most promising permitted path. Several of the promoters above sell here. Next: a free account and token, then confirm whether organizer event lists are readable for public events, and read the current terms while signed in. |
| **JamBase** | Already integrated nationally. | Covers touring stars at mainstream rooms, not the community circuit. |
| **Ticket Fairy** | Documented public API, no key. The earlier probe found no relevant Concerts. | Not useful for this gap. |
| **Promoter websites** | Bollywood Events and Radio5 run their own calendars. Neither page links a feed. Calendars were stale (past dates under "Upcoming"). | Ask the promoter for permission or an export only if Eventbrite and Sulekha both fail. Not worth scraping. |
| **Music of Our Desire, Simply Desi, AllEvents** | Listing aggregators of the same events. | Second-hand copies. Prefer the original seller. |

## Recommendation

1. **Eventbrite organizer roster.** With a free Eventbrite token, keep a short, reviewed list of South Asian promoters' Eventbrite organizer IDs. Have the daily `/sync` read their public upcoming events into the Catalog with `source="eventbrite"`. That respects the terms: title and link back, and past events are dropped already. It is curated by the owner, so it grows one promoter at a time. Start with the Los Angeles and Orange County promoters above, then the Bay Area and other metros the family uses.
2. **Ask Sulekha for a feed.** They hold most of the circuit. The request below asks for exactly what the Catalog needs.
3. **Filter to music.** Both sources mix in galas, comedy and workshops. Keep Concerts and music nights; leave everything else out. Use the source's category where it has one, and never let a model turn a title into a performer (ADR 0002).

Global coverage follows the same pattern: Eventbrite organizers and Sulekha already span the US and Canada. The earlier research names regional sellers for the UK, Gulf and India, none with self-serve discovery access.

## Draft feed request to Sulekha

> Subject: Event feed request for Concert Scout, a non-commercial Concert finder
>
> Hello Sulekha Events team,
>
> I build Concert Scout (concertscout.app), a free, non-commercial portfolio app that recommends upcoming Concerts from a listener's taste. Many of the Concerts my family and friends attend in Southern California are listed only on Sulekha, and your terms rightly rule out scraping, so I am asking whether you offer a permitted feed or API.
>
> What I would use, for upcoming music events in the US and Canada only: event ID, title, category, start date and time with time zone, venue name, address and coordinates, organizer, named performers if you record them, status (cancelled, postponed), price range, image, and the Sulekha event URL. A daily update with changes would be plenty.
>
> Every listing would link straight to its Sulekha page to buy tickets, credit Sulekha visibly, and drop past events. I would not resell, republish in bulk, or share the data. I am happy to follow any attribution, caching or rate rules you set.
>
> Thank you,
> Atherv Vidhate
> https://atherv.com

## Not done

- No Eventbrite account, token or API call. Organizer-endpoint behaviour for unrelated public events is unverified.
- No outreach to Sulekha or any promoter.
- No count of how many circuit Concerts each source would add. The Sulekha listings above are a sample from one page on one day.
