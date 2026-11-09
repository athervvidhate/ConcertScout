import type { Metadata } from "next";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = {title: "Privacy · Concert Scout"};

export default function PrivacyPage() {
  return (
    <main className="scout information">
      <SiteHeader />
      <header><h1>Privacy</h1></header>
      <article>
        <p>Concert Scout finds live music from a Taste and a place. You can Search without an account. This page describes what the app sends, keeps, and lets you remove.</p>
        <h2>Searches and imported Taste</h2>
        <p>Your Search text and imported Artist names go to the API. Anthropic processes Search text to read your request, and Taste with a shortlist to rank Concerts. Public Artist information comes from MusicBrainz, ListenBrainz, Last.fm, Ticketmaster and JamBase. Place names go to Geoapify.</p>
        <p>A Last.fm or ListenBrainz username is sent to that service when you import it. The app does not keep the username. The imported Artist list stays in your browser and accompanies later Searches until you remove it.</p>
        <p>History files, including Spotify history, are read on your device. The file contents are not uploaded. Only the resulting Artist list leaves the browser with a Search. A pasted list works the same way.</p>
        <h2>Your location</h2>
        <p>Browser location is requested only when you press the location button. Coordinates go to the API for any Search that names no place and for your Spotify shelf, and stay on this device until you press Forget my location or clear site storage. The app does not infer a place from your IP address. Ticketmaster receives a rounded search point or a state filter.</p>
        <h2>Artist details</h2>
        <p>Opening an Artist sends their name to Last.fm and to Spotify’s public catalog to show their details and page. This uses the app’s own credentials, not your accounts.</p>
        <h2>Data sources</h2>
        <p>
          Concert and Artist data comes from{" "}
          <a href="https://www.ticketmaster.com" target="_blank" rel="noopener noreferrer">Ticketmaster</a>,{" "}
          <a href="https://www.jambase.com" target="_blank" rel="nofollow noopener noreferrer">JamBase</a>,{" "}
          <a href="https://musicbrainz.org" target="_blank" rel="noopener noreferrer">MusicBrainz</a>,{" "}
          <a href="https://listenbrainz.org" target="_blank" rel="noopener noreferrer">ListenBrainz</a>,{" "}
          <a href="https://www.last.fm" target="_blank" rel="noopener noreferrer">Last.fm</a>,{" "}
          <a href="https://www.geoapify.com" target="_blank" rel="noopener noreferrer">Geoapify</a>,{" "}
          <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> and{" "}
          <a href="https://open.spotify.com" target="_blank" rel="noopener noreferrer">Spotify</a>.
        </p>
        <h2>Images</h2>
        <p>Ticket photos load directly from Ticketmaster, so Ticketmaster sees your IP address when they appear. JamBase photos pass through this site’s image cache; your browser does not request them directly from JamBase.</p>
        <h2>Reports about a Search</h2>
        <p>If you press Tell us and send a report, your Search, your note, how the app read the Search, any error and the results on screen go to the owner by email through Resend. Your location coordinates and connected Spotify data are not included. If you imported Taste, the Artists that Search used can appear in the report.</p>
        <h2>A connected Spotify account</h2>
        <p>An invited account can connect through Spotify’s own consent page. Its top Artists, top songs, followed Artists and newest 1,000 Liked Songs are used only for exact-name lookups in a separate shelf. They never enter a model, imported Taste, or localStorage.</p>
        <p>Access and refresh tokens are encrypted in Redis for at most seven days, and the Artist list for at most one day. The browser holds an opaque HttpOnly connection cookie. Disconnect Spotify inside Your Taste to delete the stored tokens, Artist list and cookie immediately. If you clear cookies first, the server entry expires on its own within seven days.</p>
        <h2>An optional account</h2>
        <p>You can create an account with Google or an email and password. Supabase stores your email, sign-in details and Saved Concerts. Google sign-in shares only your name, email and profile picture with Supabase. While you are signed in, each Saved Concert is stored in your account with the facts its source listed and its reason, and you can see it on any device you sign in on. Imported Taste, your location and any Spotify connection still stay on each device.</p>
        <p>Signing in moves any Saved Concerts made on this device before signing in into your account. Deleting your account on the Account page removes your sign-in and every Saved Concert in it at once.</p>
        <h2>What stays and for how long</h2>
        <ul>
          <li>A signed-in account keeps its Saved Concerts until you remove them or delete the account. A guest’s Saved Concerts and imported Taste stay in this browser until you remove them or clear site storage. Past Saved Concerts are hidden from the Saved page.</li>
          <li>Ticketmaster Concert data is cached for six hours, JamBase Concert data until the Concert has passed, refreshed daily, Artist metadata and similarity for seven days, and place lookups for thirty days.</li>
          <li>Hourly limits use a hash of the client address, not a raw address in Redis. Spend counters hold numeric totals.</li>
          <li>App traces record step times, token counts and cost. They omit Search text, Taste, exception contents and Spotify account data.</li>
        </ul>
        <p>Server and hosting logs may still contain connection metadata, request times and URLs, including coordinates on Spotify shelf requests. OAuth callback codes are removed from the app’s access-log scope. Hosting services and upstream providers have their own retention practices.</p>
        <h2>Other services</h2>
        <p>Cloudflare Turnstile checks requests for automation. The app adds no ads, advertising analytics or affiliate parameters. Upstream services process the requests they receive under their own policies.</p>
        <h2>Your controls</h2>
        <p>Remove a Saved Concert on the Saved page. Sign out or delete your account on the Account page. Remove imported Taste inside Your Taste. Press the location button again, labelled Forget my location, to delete the stored location. Disconnect Spotify before clearing cookies. Browser site settings can clear all remaining local choices.</p>
        <p>For questions, contact <a href="https://atherv.com" target="_blank" rel="noopener noreferrer">Atherv Vidhate through the portfolio</a>.</p>
        <p className="information-date">Updated November 8, 2026.</p>
      </article>
    </main>
  );
}
