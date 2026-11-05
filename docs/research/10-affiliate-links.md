# 10 - Affiliate links for ticket sites (as of 2026-11-04)

All pages below were fetched on 2026-11-04 unless stated. Search-snippet and aggregator figures are marked as such. Anything not read from a primary page is UNVERIFIED.

## Answer

**Can you get affiliate links? Yes, for Ticketmaster and several resale sites. But it is not worth switching on now.**

- Ticketmaster runs a public affiliate programme on Impact. It is built for sites and apps, and the Discovery API appends tracking for you once your Impact publisher ID is saved in the developer portal.
- The Developer Terms ban deriving revenue from the API, and they contain no affiliate exception. The affiliate FAQ separately says approved affiliates get a Discovery API key and automatic tracking. The two documents are not reconciled anywhere I could read. Treat the legal position as unconfirmed until Ticketmaster says so in writing.
- At portfolio traffic the income is roughly $0 to a few dollars a month. It would not reach a payout threshold for a long time.
- Turning on affiliate links changes four other things: Vercel Hobby (likely commercial), Last.fm (commercial), JamBase free tier (commercial), and FTC disclosure (required).

**Recommendation:** Keep plain outbound links now. Do not apply yet. If you later want affiliate income:
1. Email Ticketmaster developer support and the Impact programme contact, and ask for written confirmation that Discovery API use is allowed for approved affiliates.
2. Apply on Impact.
3. Move hosting to Vercel Pro (or another host).
4. Drop Last.fm in favour of ListenBrainz and MusicBrainz core data (CC0).
5. Add a visible FTC disclosure next to each link.

---

## 1. Ticketmaster

### Programme
- **Network:** Impact. "Please sign up to our Ticketmaster Global Affiliate Program via this link" (links to app.impact.com). Also findable in the Impact Marketplace under "Ticketmaster". https://developer.ticketmaster.com/partners/distribution-partners/affiliate-sign-up
- **Markets:** one application covers "all Ticketmaster markets listed below (may change over time)" across North America, LATAM, EMEA and APAC. Approval can carry "some exceptions depending on your audience and business category". Same page.
- **Inventory:** events from Ticketmaster, Ticketweb, Universe, Biletix, Front Gate Tickets, Moshtix, Veeps, Quicket. Same page.
- **Who can join:** the FAQ says the programme "is ideally designed for websites and apps capable of bringing distinct and unique audiences". There is no individual-vs-company rule in the text. Onboarding says to contact Ticketmaster first "to determine if you meet the program's requirements", then create an Impact publisher account. https://developer.ticketmaster.com/support/faq/ (Affiliates section).
- **Approval criteria:** not published. "Approval at Ticketmaster's discretion" comes from an aggregator (Lasso), not a primary source. Whether a solo developer with a portfolio app passes is UNVERIFIED.
- **Two accounts needed:** "Impact serves as the central platform for managing all aspects of our business relationship". You also need the Developer Portal key. FAQ, same section.

### Link building and the Discovery API
- Manual links: "use your Impact publisher ID to wrap destination URLs in Impact click tracking" (FAQ).
- API: "If you opt to utilize our API or Feed, this click tracking will be automatically applied to your links." You add the publisher ID in the developer portal (Edit Profile, per the FAQ as summarised by search). So the Discovery `url` field becomes affiliate-ready after the ID is saved. I did not see a sample response, so the exact URL shape is UNVERIFIED.
- Approved affiliates receive "An API key or other content tools to access the Discovery API" (FAQ). Quota stated there: 2 requests per second and 5,000 per day. This differs from the 5 rps on the getting-started page noted in 01-data-sources.md. Check the live value in your portal.

### Commission, cookie, exclusions
- Primary sources give no rate. The programme page says to read "the local commission offering in the individual market contracts within Impact". The FAQ says it "rewards partners based on actual sales generated, not just traffic referrals". Rates are visible only inside Impact after you apply.
- Exclusion (FAQ): "Ticketmaster does not provide commission for primary ticket sales during presales or within the initial 24 hours" after public onsale. This hits the highest-demand sales.
- Aggregator figures (secondary, conflicting, treat as UNVERIFIED):
  - 1% per sale (Lasso, TapRefer).
  - Up to 2% (Travelpayouts, article updated 2021-09-20, 17 European markets, "The cookie lifetime is 30 days").
  - Up to about 4.15% depending on region (search summary).
  - 30-day cookie is the commonest figure. Some regional listings show 1 to 3 days.
- Per-country table: not obtainable without an Impact login. UNVERIFIED.

### Do the terms conflict?
Developer Terms of Use, https://developer.ticketmaster.com/support/terms-of-use/ ("Last Updated: June 27, 2023", fetched 2026-11-04). Under "You shall not", item 11:
> "derive revenues from the use or provision of the Ticketmaster API ... whether for direct commercial or monetary gain or otherwise"

The clause ends "except as set forth below", but no exception follows. The page never mentions affiliates beyond a nav link to the FAQ. The Partner API terms (https://developer.ticketmaster.com/support/terms-of-use/partner/, no date shown) repeat the same clause and also have no affiliate carve-out.

On the other side, the affiliate FAQ expects affiliates to use the API and says tracking is applied automatically. The same company's documents point both ways. My reading is that the affiliate route is intended and allowed for approved affiliates, and the general ban targets selling or monetising the API itself. The text does not say so. I did not find a source that settles it. Get it in writing.

Other relevant terms in the same page:
- Caching: "Cache or store any Event Content other than for reasonable periods in order to provide the service you are providing."
- Advertising: you must disclose "that third parties (including advertisers) may serve content and/or advertisements".

---

## 2. Other programmes

Almost none of this could be read from a primary page. Commission figures are aggregator or search summaries and conflict. Real rates only appear inside each network after approval.

| Site | Programme? | Network | Individuals? | Commission (secondary) |
|---|---|---|---|---|
| Live Nation | Only an old CJ programme (2009 TicketNews) and a merch listing on FlexOffers "not currently offered". Live Nation venue/tickets now sold via Ticketmaster, so use TM | - | - | UNVERIFIED |
| AXS | No classic publisher programme found; "AXS Anywhere" is a partner model. An AXS UK listing on Impact appears on a directory | Impact (UK, directory only) | UNVERIFIED | UNVERIFIED |
| SeatGeek | Yes (migrated to Impact, "CPA structure using dynamic commissioning" per an agency case study; also on FlexOffers) | Impact, FlexOffers | Directories say individuals allowed. UNVERIFIED | 2-5% (Impact) vs 0.4-0.8% (FlexOffers); cookie 30 d vs ~2 d. UNVERIFIED |
| StubHub | Yes. Official page https://stubhub.com/affiliates did not render the terms | Impact (per directories) | UNVERIFIED | Partnerize/affi.io: 4%, MLB 0.8%; others say 9%, 3.2%, 6.4%. 30-day cookie. UNVERIFIED |
| Vivid Seats | Yes | Impact | UNVERIFIED | Commonly 6%, others 0.8-4%. 30-day cookie. UNVERIFIED |
| TickPick | Yes | Impact (directory); originally CJ in 2017 press release | UNVERIFIED | 4-5%, US only. UNVERIFIED |
| Gametime | Yes | FlexOffers listing | UNVERIFIED | Not found; 30-day cookie. UNVERIFIED |
| Viagogo | Yes | Partnerize and others | UNVERIFIED | 6.4-7%. UNVERIFIED |
| DICE | Nothing found | - | - | UNVERIFIED |
| Eventbrite | Conflicting: FlexOffers/Admitad/Impact listings vs a claim of no public programme | Various | UNVERIFIED | About 10% of Eventbrite's service fee, not ticket price. UNVERIFIED |
| See Tickets | UK programme on Awin | Awin | UNVERIFIED | Not found; 1-day cookie per FlexOffers. UNVERIFIED |
| Bandsintown | Old TechCrunch article: 50/50 split of ticket-partner revenue. Current status and access UNVERIFIED. 01-data-sources.md found its API artist-only | - | - | UNVERIFIED |

Searches used: SeatGeek, StubHub, Vivid Seats, TickPick/Viagogo, Eventbrite, AXS/DICE/Bandsintown, run 2026-11-04. Aggregators named include UpPromote, Lasso, FlexOffers, affi.io, Partnerize.

A multi-vendor "compare prices" view needs separate applications and separate event matching (see section 4 of 01-data-sources.md). That is significant extra work for tiny revenue.

---

## 3. Earnings at low traffic and payouts

**Payout:** Impact's official help says the Autopay minimum is $10 USD or local equivalent (via search of help.impact.com, not read in full). Brands set their own locking period, up to 90 days when set in days, then invoicing and a payment schedule. Some third-party reviews say $50; I trust the official $10. Lasso lists a $50 threshold for Ticketmaster and StubHub; UNVERIFIED.

**Illustrative estimate (my assumptions, not sourced):**
- 100 outbound ticket clicks a month.
- 2% of clicks become an order.
- An average order of $120 (two tickets).
- A commission of 1.5%.

100 x 2% x $120 x 1.5% = **$3.60 a month**. Even with 1,000 clicks it is about $36 a month. Presale and first-24-hour exclusions, refunds and reversals push real income lower. A portfolio app is more likely to see tens of clicks than hundreds.

Time to reach $10 at the base case is about three months, plus the locking period. Net effect: negligible income.

---

## 4. Knock-on effects

### Vercel Hobby
https://vercel.com/docs/limits/fair-use-guidelines (page `last_updated: 2026-09-14`):
> "Hobby teams are restricted to non-commercial personal use only. All commercial usage of the platform requires either a Pro or Enterprise plan."

> "Commercial usage is defined as any Deployment that is used for the purpose of financial gain of anyone involved in any part of the production of the project..."

List of examples includes (re-fetched 2026-11-04):
> "Advertising the sale of a product or service"
> "Affiliate linking is the primary purpose of the site"
> "The inclusion of advertisements..."
> "Asking for Donations does not fall under commercial usage."

Does an affiliate link count? The definition is "financial gain of anyone involved", and the example is limited to sites where affiliate linking is "the primary purpose". Concert Scout's purpose is discovery, with outbound ticket links as the main monetisable action. Literal reading: affiliate links to buy tickets are close to the primary purpose, so treat as commercial. Not certain. Vercel says to contact support if unsure. Move to Pro (price not verified here) or contact Vercel first.

### Last.fm API
https://www.last.fm/api/tos:
> "You are permitted to use the Last.fm Data solely for non-commercial purposes and for no other purpose."

"Non-commercial" is not defined on the page. Clause 3.1 says "If you are unsure whether your use of the Last.fm Data constitutes non-commercial or commercial use, you should contact us." Clause 3.2: "you must apply for a commercial use agreement"; commercial use without one is a "material breach" allowing immediate termination. The summary says Last.fm "reserves the right to share in revenue generated from your use of Last.fm Data in future". Affiliate commissions are revenue, so assume commercial. Drop Last.fm if affiliates go live.

### ListenBrainz / MusicBrainz
- MusicBrainz core data: "The core data of the database is licensed under the CC0." Supplementary data (tags, ratings, etc.) is CC BY-NC-SA 3.0 and non-commercial. https://musicbrainz.org/doc/About/Data_License. Use core data only (MBIDs, names, relationships), and avoid supplementary tags if commercial.
- ListenBrainz data licence and any commercial API fee: not found on https://metabrainz.org/api. UNVERIFIED. Check the MetaBrainz pages before launch.

### JamBase
https://data.jambase.com/pricing lists the Developer tier intended use as "Non-commercial" with "Attribution required". It does not define the term or address affiliate or ticket links. Developer Terms at /legal/developer-terms were not read. UNVERIFIED whether affiliate links count as commercial. Assume yes. The paid Startup tier is $500 a month, which dwarfs any commission.

### FTC
- FTC Endorsement Guides FAQ, https://www.ftc.gov/business-guidance/resources/ftcs-endorsement-guides-what-people-are-asking:
  > "You should disclose your relationship to the retailer clearly and conspicuously on your site."
  > Suggested wording: "I get commissions for purchases made through links in this post."
  > "'Paid link' right next to an affiliate link should be an adequate disclosure." "'Commissionable link' is probably not a clear disclosure." A "buy now" button also wouldn't be adequate.
  > "The disclosure should catch users' attention and be placed where they aren't likely to miss it."
- The FTC Disclosures 101 page says the disclosure belongs "with the endorsement message itself", not buried on an About page. https://www.ftc.gov/business-guidance/resources/disclosures-101-social-media-influencers
- Practical rule: a short line near each ticket button, for example "We may earn a commission if you buy through this link", plus a page-level note. If the link is not paid, no disclosure is needed.
- The eCFR text of 16 CFR Part 255 could not be fetched (redirect). Rely on the FAQ above.
- UK and EU users: UK ASA/CMA rules are UNVERIFIED and not researched.

---

## Checklist if you proceed later
1. Email Ticketmaster developer support: may an approved affiliate earn commission on Discovery API links, given Developer Terms item 11? Keep the reply.
2. Apply on Impact; read the per-market contracts for rates, locking and payment terms.
3. Move off Vercel Hobby; remove Last.fm; check JamBase and MetaBrainz commercial terms.
4. Save the publisher ID in the developer portal; confirm tracking appears on Discovery `url` values.
5. Add the FTC disclosure beside each outbound link.
