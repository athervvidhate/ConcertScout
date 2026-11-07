import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

export const metadata: Metadata = {title: "Data credits · Concert Scout"};
const sources = [
  {name: "Ticketmaster", url: "https://www.ticketmaster.com", text: "Concert names, Lineups, dates, times, venues, prices and Ticket links come from the Discovery API. Source facts are kept unchanged; missing facts stay absent."},
  {name: "MusicBrainz", url: "https://musicbrainz.org", text: "Artist identities, name aliases and tags come from the MusicBrainz community and MetaBrainz Foundation."},
  {name: "ListenBrainz", url: "https://listenbrainz.org", text: "Artist similarity and tags come from ListenBrainz and MetaBrainz. Its Labs similarity endpoint can be unavailable, so the app has a fallback."},
  {name: "Last.fm", url: "https://www.last.fm", text: "Powered by AudioScrobbler / Last.fm. Similar Artists provide a fallback, and a visitor can import top Artists using a public username."},
  {name: "Geoapify", url: "https://www.geoapify.com", text: "Place names and coordinates are resolved through Geoapify. Map data includes OpenStreetMap contributors."},
];

export default function CreditsPage() {
  return (
    <main className="scout information">
      <header><h1>Data credits</h1><Link href="/">Back to Search</Link></header>
      <article>
        <p>A Poster combines real Concert facts with a reason for each Recommendation. These are the services and communities that make it possible.</p>
        <dl className="source-credits">{sources.map(source => (
          <div key={source.name}><dt><a href={source.url} target="_blank" rel="noopener noreferrer">{source.name}</a></dt><dd>{source.text}</dd></div>
        ))}</dl>
        <p>MusicBrainz publishes its <a href="https://musicbrainz.org/doc/About/Data_License" target="_blank" rel="noopener noreferrer">data licenses</a>. Geographic data is credited to <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap contributors</a>. Last.fm’s <a href="https://www.last.fm/api/tos" target="_blank" rel="noopener noreferrer">API terms</a> apply to its data.</p>
        <section className="spotify-credit" aria-label="Spotify attribution">
          <Image src="/spotify-logo-white.svg" alt="Spotify" width={110} height={34} />
          <p>When an invited account connects, Spotify supplies top and followed Artist names and links for a separate shelf. Those names link back to Spotify and never enter a model. A user-held history file is a separate, local import.</p>
          <a href="https://open.spotify.com" target="_blank" rel="noopener noreferrer">Open Spotify</a>
        </section>
        <h2>Interpretation and ranking</h2>
        <p>Anthropic’s Claude Haiku interprets a Search and ranks shortlisted Concert IDs. Code rejects unknown IDs and fills every Concert fact from Ticketmaster. Model reasons are judgments, so a short Poster is better than filler.</p>
        <h2>Design and project</h2>
        <p>Concert Scout is a non-commercial project by <a href="https://atherv.com" target="_blank" rel="noopener noreferrer">Atherv Vidhate</a>. Its screen-printed Poster design uses Anton, Big Shoulders, Bricolage Grotesque, Hanken Grotesk and Doto, self-hosted by the app.</p>
        <p><a href="https://github.com/athervvidhate/ConcertScoutAI" target="_blank" rel="noopener noreferrer">Read the source and architecture</a>.</p>
      </article>
    </main>
  );
}
