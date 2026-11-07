"use client";

import { Button } from "@base-ui/react/button";
import Image from "next/image";
import { useEffect, useState } from "react";

import { formatDate, formatTime } from "@/lib/format";
import type { Concert } from "@/lib/search";
import { SPOTIFY_ROOT, type SpotifyConnection } from "@/lib/spotify";

export function SpotifyControl({connection}: {connection: SpotifyConnection}) {
  return (
    <section className="spotify-control" aria-label="Spotify connection">
      <h3>Connect Spotify</h3>
      <p>Invited accounts get a separate shelf from their top Artists. It never goes to a model.</p>
      {connection.connected ? <Button onClick={connection.disconnect}>Disconnect Spotify</Button> :
        connection.available && connection.connectHref ?
          <a href={connection.connectHref} target="_blank" rel="noopener noreferrer">Connect Spotify</a> :
          <p>Spotify connections are not available yet. You can use your history file instead.</p>}
      {connection.message && <p role="status">{connection.message}</p>}
    </section>
  );
}

type Item = {concert: Concert; artist: {name: string; url: string; followed: boolean}};
type Props = {connectHref: string | null; place?: string; lat?: number; lon?: number; start?: string; end?: string};

export function SpotifyShelf({connectHref, place, lat, lon, start, end}: Props) {
  const [items, setItems] = useState<Item[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const hasPlace = !!place || (lat !== undefined && lon !== undefined);

  useEffect(() => {
    if (!hasPlace) return;
    const controller = new AbortController();
    const params = new URLSearchParams();
    if (place) params.set("place", place);
    else if (lat !== undefined && lon !== undefined) {
      params.set("lat", String(lat)); params.set("lon", String(lon));
    }
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    async function load() {
      try {
        const response = await fetch(`${SPOTIFY_ROOT}/shelf?${params}`, {credentials: "include", cache: "no-store", signal: controller.signal});
        const body = await response.json();
        if (!response.ok) setError(body.message);
        else setItems(body.concerts);
      } catch {
        if (!controller.signal.aborted) setError("Your Spotify shelf could not load. Try again soon.");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    load();
    return () => controller.abort();
  }, [end, hasPlace, lat, lon, place, start]);

  return (
    <section className="spotify-shelf" aria-label="Concerts from your Spotify top Artists">
      <header>
        <div><h2>From your top Artists</h2><p>Your Spotify shelf</p></div>
        <Image src="/spotify-logo-white.svg" alt="Spotify" width={110} height={34} />
      </header>
      {!hasPlace ? <p>Search a place or use your location to see Concerts from your top Artists.</p> :
        loading ? <p role="status">Looking for Concerts by your top Artists</p> :
          error ? <div role="alert"><p>{error}</p>{connectHref && <a href={connectHref} target="_blank" rel="noopener noreferrer">Reconnect Spotify</a>}</div> : items.length === 0 ?
            <p>No Concerts from your top Artists here in these dates. Try wider dates or a nearby city.</p> :
            <ul>{items.map(({concert, artist}) => (
              <li key={concert.id}>
                <a href={artist.url} target="_blank" rel="noopener noreferrer" className="spotify-artist">{artist.name}</a>
                <p>{concert.name}</p>
                <p>{[concert.date && formatDate(concert.date), concert.time && formatTime(concert.time), concert.venue, concert.city].filter(Boolean).join(" · ")}</p>
                <span>{artist.followed ? "An Artist you follow" : "From your top Artists"}</span>
                <a href={concert.url} target="_blank" rel="noopener noreferrer" className="spotify-tickets">Tickets</a>
              </li>
            ))}</ul>}
    </section>
  );
}
