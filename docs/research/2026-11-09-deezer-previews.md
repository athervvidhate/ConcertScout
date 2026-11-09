# Deezer Previews: do the terms allow them?

November 9, 2026. Gate for issue #87: do Deezer's developer terms clearly allow a public, non-commercial site to play the 30-second clips from the Artist panel, with credit? **They do not clearly allow it.** The owner then chose option 2, Spotify's artist embed, which is checked in the last section. Issue #87 uses Spotify, not Deezer.

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
2. **Spotify artist embed.** `ArtistProfile.spotify_url` already exists. Spotify's official embed (an iframe built from the Artist's Spotify URL) plays clips inside Spotify's own player with no API access, no key and no Concert Scout audio handling. Its terms are read in the section below. It involves no Spotify account data, but it is a third-party iframe, not a native `<audio>` control styled to the design.
3. **Drop audio.** Keep the Artist panel as links (Last.fm top tracks, Spotify link) and let people open the Artist elsewhere.

## Spotify's artist embed: do the terms allow it?

Checked on the same date, from the developer pages' text. **Yes, with four duties.** Issue #87 builds it.

Sources:

- [Embeds overview](https://developer.spotify.com/documentation/embeds)
- [Creating an Embed](https://developer.spotify.com/documentation/embeds/tutorials/creating-an-embed) (sizes and Spotify's own iframe snippet)
- [Widget Terms](https://developer.spotify.com/documentation/embeds/terms)

What the terms require:

1. **Accept the Developer Terms.** "By using Spotify Embeds, you accept the Spotify Developer Terms of Service" (overview, Legal). Showing an embed is the acceptance. There is no key, login or app registration.
2. **Show it unaltered, unobscured.** Widget Terms IV.3.a: display the widgets "in the form made available by Spotify, without alteration". IV.3.b: do not "obfuscate the Spotify Widgets in any way, whether by banner advertisements or by any other means, or alter the form or format". So no overlay, restyling, cropping or hiding. The iframe may keep its own `border-radius: 12px` from Spotify's snippet.
3. **Size.** "Make the container at least 280 pixels wide for an audio Embed"; use 152 or 352 pixels high for new placements (232 and 80 are legacy). An Artist embed at 352 shows the top tracks list.
4. **Disclose cookies.** Widget Terms III.3: Spotify "places cookies and similar technologies ... and causes third party Cookies to be placed, on the browsers of users that visit websites that embed Spotify Widgets". V.6 requires a "complete and accurate disclosure to end users" of the site's cookie use and of third parties placing cookies. The privacy page now says so.

Other terms that matter here:

- The widget may be shown only on a site the developer controls (III.1.a). The embed is only on concertscout.app.
- The site must have a privacy policy (V) and must not target children under 13 (V). Concert Scout is not aimed at children.
- Spotify may revoke access at any time (VI), so the Listen button is an optional extra with no other feature depending on it.

The embed involves no Spotify account data. The page and the iframe URL are public catalog values, so nothing reaches a model ([ADR 0003](../adr/0003-official-spotify-access-only.md)).

Spotify's own snippet, which the iframe copies (minus the `utm_source` query):

```html
<iframe style="border-radius: 12px" src="https://open.spotify.com/embed/track/..." width="100%" height="352"
  frameborder="0" allowfullscreen="" allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"
  loading="lazy"></iframe>
```

Observed in headless Chromium with no Spotify login (the embed for Radiohead, `4Z8W4fKeB5YxbusRsdQVPb`):

- It plays inside Spotify's own player and shows a "Preview" badge, which is Spotify's mark for 30-second clips when nobody is signed in. Headless Chromium cannot play audio, so no clip was heard.
- Loading the iframe at once sets `sp_t` and `sp_landing` on `.spotify.com`, and requests go to `open.spotify.com`, `embed-cdn.spotifycdn.com`, `image-cdn-fa.spotifycdn.com`, `encore.scdn.co`, `apresolve.spotify.com`, `guc3-spclient.spotify.com` and a Sentry ingest host. This is why the iframe loads only after the person presses Listen.

The Next.js app sets no Content-Security-Policy; the API's `default-src 'none'` header applies to API responses only. So no `frame-src` change is needed. If a policy is added later, it must allow `frame-src https://open.spotify.com`.
