import Link from "next/link";

import { ArtistPanel } from "@/components/artist-panel";
import { nameOf } from "@/components/ticket";
import { formatDate } from "@/lib/format";
import type { Recommendation } from "@/lib/search";

/** Where a Poster ends, once every Ticket has been decided. */
export function PosterDone({ saved }: { saved: Recommendation[] }) {
  if (saved.length === 0) {
    return (
      <section className="poster-done" aria-live="polite">
        <h2>Nothing saved this time</h2>
        <p>Try other dates or a different sound. To look again, tap a name on the Poster.</p>
      </section>
    );
  }
  return (
    <section className="poster-done" aria-live="polite">
      <h2>You saved {saved.length === 1 ? "1 Concert" : `${saved.length} Concerts`}</h2>
      <ul>
        {saved.map((recommendation) => {
          const { date, venue, city } = recommendation.concert;
          return (
            <li key={recommendation.concert.id}>
              <ArtistPanel name={nameOf(recommendation)} />
              <span>{[date && formatDate(date), venue, city].filter(Boolean).join(", ")}</span>
            </li>
          );
        })}
      </ul>
      <Link href="/saved">See your Saved Concerts</Link>
    </section>
  );
}
