"use client";

import { Button } from "@base-ui/react/button";
import { useEffect, useRef, useState } from "react";

import { formatDate, formatTime } from "@/lib/format";
import { keepNearbyHidden, type Place, readNearbyHidden, useNearby } from "@/lib/nearby";
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

type Props = {
  place: Place;
  onForget: () => void;
  /** After a request for this section, which sits at the bottom of a long page. */
  scrollTo: boolean;
};

export function NearbyConcerts({ place, onForget, scrollTo }: Props) {
  const [hidden, setHidden] = useState(readNearbyHidden);
  const section = useRef<HTMLElement>(null);
  // Hidden Concerts cost no lookup.
  const nearby = useNearby(hidden ? null : place);

  useEffect(() => {
    if (scrollTo) section.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [scrollTo]);

  function toggle() {
    keepNearbyHidden(!hidden);
    setHidden(!hidden);
  }

  return (
    <section ref={section} className="nearby" aria-label="Concerts near you">
      <header>
        <h2>Concerts near you</h2>
        <Button type="button" aria-expanded={!hidden} onClick={toggle}>
          {hidden ? "Show" : "Hide"}
        </Button>
      </header>
      {!hidden && (
        <>
          <div aria-live="polite">
            {nearby.loading && <p>Looking for Concerts nearby</p>}
            {nearby.error && <p>{nearby.error}</p>}
            {nearby.empty && (
              <p>No Concerts found in the next month. Search a nearby city instead.</p>
            )}
          </div>
          {nearby.concerts.length > 0 && (
            <ul className="nearby-list">
              {nearby.concerts.map((concert) => (
                <NearbyConcert key={concert.id} concert={concert} />
              ))}
            </ul>
          )}
        </>
      )}
      <Button type="button" className="nearby-forget" onClick={onForget}>
        Forget my location
      </Button>
    </section>
  );
}
