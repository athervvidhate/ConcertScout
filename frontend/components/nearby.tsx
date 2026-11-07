"use client";

import { Button } from "@base-ui/react/button";

import { formatDate, formatTime } from "@/lib/format";
import { type Place, useNearby } from "@/lib/nearby";
import type { Concert } from "@/lib/search";

function NearbyConcert({ concert }: { concert: Concert }) {
  const when = [
    concert.date && formatDate(concert.date),
    concert.time && formatTime(concert.time),
  ].filter(Boolean);
  return (
    <li>
      <a href={concert.url} target="_blank" rel="noopener noreferrer">
        {concert.artists[0]?.name ?? concert.name}
      </a>
      <span>{[when.join(" at "), concert.venue].filter(Boolean).join(" · ")}</span>
    </li>
  );
}

export function NearbyConcerts({ place, onClose }: { place: Place; onClose: () => void }) {
  const nearby = useNearby(place);

  return (
    <section className="nearby" aria-label="Concerts near you">
      <header>
        <h2>Concerts near you</h2>
        <Button type="button" onClick={onClose}>
          Hide
        </Button>
      </header>
      <div aria-live="polite">
        {nearby.loading && <p>Looking for Concerts nearby</p>}
        {nearby.error && <p>{nearby.error}</p>}
        {nearby.empty && <p>No Concerts found in the next month. Search a nearby city instead.</p>}
      </div>
      {nearby.concerts.length > 0 && (
        <ul className="nearby-list">
          {nearby.concerts.map((concert) => (
            <NearbyConcert key={concert.id} concert={concert} />
          ))}
        </ul>
      )}
    </section>
  );
}
