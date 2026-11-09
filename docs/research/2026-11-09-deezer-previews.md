# Deezer Previews: do the terms allow them?

November 9, 2026. Gate for issue #87: do Deezer's developer terms clearly allow a public, non-commercial site to play the 30-second clips from the Artist panel, with credit? **They do not clearly allow it.** Work on #87 stops here until the owner decides.

Sources read on this date (page text fetched directly):

- [Terms of use of Deezer for Developers](https://developers.deezer.com/termsofuse)
- [Deezer developer guidelines](https://developers.deezer.com/guidelines)
- [Simple API page](https://developers.deezer.com/api) (shows only a login prompt)
- [Deezer FAQs For Developers](https://support.deezer.com/hc/en-gb/articles/360011538897-Deezer-FAQs-For-Developers)

## What supports it

- The guidelines treat a website as a supported API platform with 30-second audio: "Website ... API: Yes*" and "*Full data access, but no audio streaming available except 30s extracts."
- The guidelines name the 30-second MP3 as the one audio URL an end user may see: "Except for 30s. extracts mp3s, full-length tracks URLs must never be accessible to the end-user from your application."
- The terms grant "free access to the DEEZER API in order to develop Webpages and/or Personal Applications", and the API serves Track and Artist content.
- The API is free: "There is no paid API" (FAQ).

## What blocks a clear yes

1. **Private, family use only.** Terms IV: "The use of the Content is limited to a strictly private use within a family scope." The same section requires the developer to "inform by any means any person accessing the Content through the Webpages and/or Personal Applications of its conditions of use and notably that the streaming of the recordings is limited to a strictly private use within a family scope." A public portfolio site played to visitors is not obviously a family-scope use, and the terms add a duty to tell every visitor.
2. **Strict non-commercial wording that a portfolio site can brush against.** Terms IV: the developer "shall not perceive, receive, generate, benefit or create directly or indirectly, any moneys, incomes, revenues, data or any other consideration in connection with the use of ... the Content accessed through the Services." Also: the Services and Content "shall not be associated, directly or indirectly with any trademark, brand name, or logo." Concert Scout is a public portfolio piece, so "indirect benefit" and "association with a brand" are arguable.
3. **"Personal" scope.** Section I describes the API as for "personal site", "personal web pages" and "Personal Applications". Terms IX: "use of the Services for any other purposes than those mentioned herein, shall be beforehand reviewed and approved by DEEZER, at DEEZER's own discretion." Nothing says a public multi-user app is covered.
4. **Terms are accepted behind a login, and the trademark rules are not public.** The Simple API page says "You have to login to accept the terms and conditions of the simple API." The issue assumes "Deezer needs no key"; the unauthenticated endpoint does work (the evals use it), but the terms treat use as an agreement made through a developer account. Terms II.a also makes the Trademark Guidelines (at that login-gated page) "full part of this Terms". Without them, I cannot confirm what credit Deezer requires or permits.
5. **Revocable at will.** Terms II.c: Deezer may "modify, restrict or remove Developer access ... at any time for any reason ... without any prior notice."
6. **Technical fact, not a terms fact.** Preview clip URLs are signed and short-lived. A live call today returned `https://cdnt-preview.dzcdn.net/.../<hash>.mp3?hdnea=exp=1794247400~acl=...~hmac=...` with `exp` about 15 minutes after the request (895 s). The issue says to cache Previews "like the rest of the profile"; a cached clip URL would be dead long before the profile cache expires, so the API would need to refresh the clip URL at play time or cache only the track id. Local/offline storage of audio is separately forbidden ("Local Storage/Offline Storage of audio data is strictly forbidden"), so the clip itself must not be proxied or stored.

## Conclusion

The guidelines make 30-second extracts on a website a normal use. The terms those guidelines point to still restrict all Content to "strictly private use within a family scope" and require the developer to tell every user so. That is not a clear permission for a public site. The FAQ offers a partnership contact form for anything beyond the free API. No implementation was started.

## Options

1. **Ask Deezer** (the FAQ's partnership/contact form, or Deezer Support) for written confirmation that a public non-commercial portfolio site may play 30-second extracts with credit, and for the Trademark Guidelines. Implement only after a yes. Also resolve the expiring-URL design (point 6).
2. **Spotify artist embed.** `ArtistProfile.spotify_url` already exists. Spotify's official embed (an iframe built from the Artist's Spotify URL) plays clips inside Spotify's own player with no API access, no key and no Concert Scout audio handling. Spotify's embed terms were not read for this note, so check them before choosing it. It involves no Spotify account data, but it is a third-party iframe, not a native `<audio>` control styled to the design.
3. **Drop audio.** Keep the Artist panel as links (Last.fm top tracks, Spotify link) and let people open the Artist elsewhere.
