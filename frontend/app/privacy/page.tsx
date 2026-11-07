import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {title: "Privacy · Concert Scout"};

export default function PrivacyPage() {
  return (
    <main className="scout information">
      <header><h1>Privacy</h1><Link href="/">Back to Search</Link></header>
      <article>
        <p>Concert Scout finds live music from a Taste and a place. You can Search without an account. This page describes what the app sends, keeps, and lets you remove.</p>
        <h2>Searches and imported Taste</h2>
        <p>Your Search text and imported Artist names go to the API. Anthropic processes Search text to read your request, and Taste with a shortlist to rank Concerts. Public Artist information comes from MusicBrainz, ListenBrainz, Last.fm and Ticketmaster. Place names go to Geoapify.</p>
        <p>A Last.fm or ListenBrainz username is sent to that service when you import it. The app does not keep the username. The imported Artist list stays in your browser and accompanies later Searches until you remove it.</p>
        <p>History files, including Spotify history, are read on your device. The file contents are not uploaded. Only the resulting Artist list leaves the browser with a Search. A pasted list works the same way.</p>
        <h2>Your location</h2>
        <p>Browser location is requested only when you press the location button. Coordinates go to the API to look for nearby Concerts, and stay on this device until you hide nearby Concerts or clear site storage. The app does not infer a place from your IP address. Ticketmaster receives a rounded search point or a state filter.</p>
        <h2>A connected Spotify account</h2>
        <p>An invited account can connect through Spotify’s own consent page. Its top and followed Artists are used only for exact-name lookups in a separate shelf. They never enter a model, imported Taste, or localStorage.</p>
        <p>Access and refresh tokens are encrypted in Redis for at most seven days. The browser holds an opaque HttpOnly connection cookie. Disconnect Spotify inside Your Taste to delete the stored tokens and cookie immediately. If you clear cookies first, the server entry expires on its own within seven days.</p>
        <h2>What stays and for how long</h2>
        <ul>
          <li>Saved Concerts, skipped choices and imported Taste stay in this browser until you remove them or clear site storage. Past Saved Concerts are hidden from the Saved page.</li>
          <li>Public Concert data is cached for six hours, Artist metadata and similarity for seven days, and place lookups for thirty days.</li>
          <li>Hourly limits use a hash of the client address, not a raw address in Redis. Spend counters hold numeric totals.</li>
          <li>App traces record step times, token counts and cost. They omit Search text, Taste, exception contents and Spotify account data.</li>
        </ul>
        <p>Server and hosting logs may still contain connection metadata, request times and URLs, including coordinates on nearby requests. OAuth callback codes are removed from the app’s access-log scope. Hosting services and upstream providers have their own retention practices.</p>
        <h2>Other services</h2>
        <p>Cloudflare Turnstile checks requests for automation. The app adds no ads, advertising analytics or affiliate parameters. Upstream services process the requests they receive under their own policies; see <Link href="/credits">data credits</Link> for those services.</p>
        <h2>Your controls</h2>
        <p>Remove a Saved Concert on the Saved page. Remove imported Taste inside Your Taste. Hide nearby Concerts to forget the stored location. Disconnect Spotify before clearing cookies. Browser site settings can clear all remaining local choices.</p>
        <p>For questions, contact <a href="https://atherv.com" target="_blank" rel="noopener noreferrer">Atherv Vidhate through the portfolio</a>.</p>
        <p className="information-date">Updated November 6, 2026.</p>
      </article>
    </main>
  );
}
