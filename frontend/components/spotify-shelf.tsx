"use client";

import { Button } from "@base-ui/react/button";
import Image from "next/image";
import { useEffect, useState } from "react";

import {formatDate, formatTime, presaleLine} from "@/lib/format";
import type { Concert } from "@/lib/search";
import { SPOTIFY_ROOT, type SpotifyConnection } from "@/lib/spotify";

export function SpotifyControl({connection}: {connection: SpotifyConnection}) {
  return (
    <section className="spotify-control" aria-label="Spotify connection">
      <h3>{connection.connected ? "Spotify connected" : "Start with Spotify"}</h3>
      <p>Invited accounts get a separate shelf from their top Artists, top songs, follows and Liked Songs. It never goes to a model.</p>
      {connection.connected ? <Button className="spotify-disconnect" onClick={connection.disconnect}>Disconnect Spotify</Button> :
        connection.available && connection.connectHref ?
          <a className="spotify-connect" href={connection.connectHref} target="_blank" rel="noopener noreferrer">Connect Spotify</a> :
          <p>Spotify connections are not available yet. You can use your history file instead.</p>}
      {connection.message && <p role="status">{connection.message}</p>}
    </section>
  );
}

type Source = "top" | "track" | "followed" | "liked";
type Item = {concert: Concert; artist: {name: string; url: string; source: Source}};
type Props = {
  connectHref: string | null;
  onLocate: () => void;
  // With no Search yet, the shelf looks two months ahead near the visitor.
  upcoming: boolean;
  place?: string;
  lat?: number;
  lon?: number;
  radius?: number;
  start?: string;
  end?: string;
  genres?: string[];
};

const SOURCE_LABELS: Record<Source, string> = {
  top: "From your top Artists",
  track: "From your top songs",
  followed: "An Artist you follow",
  liked: "From your Liked Songs",
};
const UPCOMING_DAYS = 60;
const SHELF_STEP = 5;

function upcomingEnd(): string {
  const end = new Date();
  end.setDate(end.getDate() + UPCOMING_DAYS);
  return [end.getFullYear(), String(end.getMonth() + 1).padStart(2, "0"), String(end.getDate()).padStart(2, "0")].join("-");
}

export function SpotifyShelf({connectHref, onLocate, upcoming, place, lat, lon, radius, start, end, genres}: Props) {
  const [items, setItems] = useState<Item[]>([]);
  const [shown, setShown] = useState(SHELF_STEP);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const hasPlace = !!place || (lat !== undefined && lon !== undefined);

  useEffect(() => {
    if (!hasPlace) return;
    const controller = new AbortController();
    const params = new URLSearchParams();
    if (place) {
      params.set("place", place);
      if (radius) params.set("radius", String(radius));
    }
    else if (lat !== undefined && lon !== undefined) {
      params.set("lat", String(lat)); params.set("lon", String(lon));
    }
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    else if (upcoming) params.set("end", upcomingEnd());
    for (const genre of genres ?? []) params.append("genre", genre);
    async function load() {
      try {
        const response = await fetch(`${SPOTIFY_ROOT}/shelf?${params}`, {credentials: "include", cache: "no-store", signal: controller.signal});
        const body = await response.json();
        if (!response.ok) setError(body.message);
        else {
          setItems(body.concerts);
          setShown(SHELF_STEP);
        }
      } catch {
        if (!controller.signal.aborted) setError("Your Spotify shelf could not load. Try again soon.");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    load();
    return () => controller.abort();
  }, [end, genres, hasPlace, lat, lon, place, radius, start, upcoming]);

  const remaining = items.length - shown;

  return (
    <section className="spotify-shelf" aria-label="Concerts from your Spotify Artists">
      <header>
        <div><h2>From your Artists</h2><p>{upcoming ? "Near you in the next two months" : "Your Spotify shelf"}</p></div>
        <Image src="/spotify-logo-white.svg" alt="Spotify" width={110} height={34} />
      </header>
      {!hasPlace ? (
        <div className="spotify-locate">
          <p>Share your location to see your Artists&apos; Concerts near you in the next two months.</p>
          <Button type="button" onClick={onLocate}>Use my location</Button>
        </div>
      ) :
        loading ? <p role="status">Looking for Concerts by your Artists</p> :
          error ? <div role="alert"><p>{error}</p>{connectHref && <a href={connectHref} target="_blank" rel="noopener noreferrer">Reconnect Spotify</a>}</div> : items.length === 0 ?
            <p>No Concerts from your Artists fit this. Try wider dates or a nearby city.</p> :
            <>
              <ul>{items.slice(0, shown).map(({concert, artist}) => (
              <li key={concert.id}>
                <a href={artist.url} target="_blank" rel="noopener noreferrer" className="spotify-artist">{artist.name}</a>
                <p>{concert.name}</p>
                <p>{[concert.date && formatDate(concert.date), concert.time && formatTime(concert.time), concert.venue, concert.city].filter(Boolean).join(" · ")}</p>
                {presaleLine(concert) && <p>{presaleLine(concert)}</p>}
                <span>{SOURCE_LABELS[artist.source]}</span>
                <a href={concert.url} target="_blank" rel="noopener noreferrer" className="spotify-tickets">Tickets</a>
              </li>
              ))}</ul>
              {remaining > 0 && (
                <Button type="button" className="spotify-more" onClick={() => setShown(shown + SHELF_STEP)}>
                  Show {Math.min(remaining, SHELF_STEP)} more
                </Button>
              )}
            </>}
    </section>
  );
}
