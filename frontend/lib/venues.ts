import { useEffect, useState } from "react";

import { artistKey } from "@/lib/alerts";
import { API_URL } from "@/lib/search";

export type VenueTier =
  | "Intimate club"
  | "Club / Ballroom"
  | "Theater"
  | "Amphitheater / Large hall"
  | "Arena / Stadium";

export type VenueCharacter = {
  name: string;
  city?: string;
  capacity?: number;
  tier?: VenueTier;
  venue_type?: string;
  mbid?: string;
  wikidata_id?: string;
};

export type FollowedVenue = {
  venue_key: string;
  name: string;
  city?: string | null;
  lat?: number | null;
  lon?: number | null;
};

const count = new Intl.NumberFormat("en-US");
const cache = new Map<string, VenueCharacter>();

/**
 * The key two spellings of one venue share. Mirrors the API's `venues.venue_key`, so the Follow
 * venue button knows a venue is followed before asking. The API decides what is stored.
 */
export function venueKey(name: string, city?: string | null): string {
  const venue = artistKey(name);
  if (!venue) return "";
  const place = city ? artistKey(city) : "";
  return place ? `${venue}::${place}` : venue;
}

/** Factual room character summary for Tickets, or null when unverified. */
export function formatVenueCharacter(venue: VenueCharacter): string | null {
  const parts: string[] = [];
  if (venue.tier) parts.push(venue.tier);
  if (typeof venue.capacity === "number" && venue.capacity > 0) {
    parts.push(`${count.format(venue.capacity)} cap`);
  }
  if (parts.length > 0) return parts.join(" · ");
  if (venue.venue_type) return venue.venue_type;
  return null;
}

function queryKey(name: string, city?: string, lat?: number, lon?: number): string {
  const coords = lat !== undefined && lon !== undefined ? `${lat.toFixed(3)},${lon.toFixed(3)}` : "";
  return `${venueKey(name, city)}|${coords}`;
}

/** Lazily loads verified room character when a Ticket renders. Never blocks or throws. */
export function useVenueCharacter(
  name?: string,
  city?: string,
  lat?: number,
  lon?: number,
): VenueCharacter | null {
  const key = name ? queryKey(name, city, lat, lon) : "";
  const [loaded, setLoaded] = useState<{ key: string; value: VenueCharacter } | null>(() => {
    const existing = key ? cache.get(key) : undefined;
    return existing ? { key, value: existing } : null;
  });

  useEffect(() => {
    if (!name || !key) return;
    if (cache.has(key)) return;

    const controller = new AbortController();
    const params = new URLSearchParams({ name });
    if (city) params.set("city", city);
    if (lat !== undefined && lon !== undefined) {
      params.set("lat", String(lat));
      params.set("lon", String(lon));
    }
    fetch(`${API_URL}/venue?${params}`, { signal: controller.signal })
      .then((response) => (response.ok ? (response.json() as Promise<VenueCharacter>) : null))
      .then((value) => {
        if (!value || controller.signal.aborted) return;
        cache.set(key, value);
        setLoaded({ key, value });
      })
      .catch(() => {});
    return () => controller.abort();
  }, [name, city, lat, lon, key]);

  if (!key) return null;
  return cache.get(key) ?? (loaded?.key === key ? loaded.value : null);
}
