import { useEffect, useState } from "react";

import { API_URL, type Concert, type SearchError } from "@/lib/search";

export type Place = { name: string; lat: number; lon: number };

const PLACE_KEY = "concert-scout-place";

async function getJson<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { signal });
  if (!response.ok) {
    const error: SearchError = await response.json();
    throw new Error(error.message);
  }
  return response.json();
}

export async function findPlaces(text: string, signal: AbortSignal): Promise<Place[]> {
  const query = new URLSearchParams({ text });
  return (await getJson<{ places: Place[] }>(`/places?${query}`, signal)).places;
}

export async function findNearby({ lat, lon }: Place, signal: AbortSignal): Promise<Concert[]> {
  const query = new URLSearchParams({ lat: String(lat), lon: String(lon) });
  return (await getJson<{ concerts: Concert[] }>(`/nearby?${query}`, signal)).concerts;
}

/** Only a place the visitor chose lands here. It stays on this device. */
export function readPlace(): Place | null {
  try {
    return JSON.parse(localStorage.getItem(PLACE_KEY) ?? "null");
  } catch {
    return null;
  }
}

export function keepPlace(place: Place): void {
  try {
    localStorage.setItem(PLACE_KEY, JSON.stringify(place));
  } catch {
    // Without storage, the visitor only has to choose the place again next time.
  }
}

type NearbyResult = { place: Place; concerts: Concert[]; error: string | null };

export type NearbyState = { loading: boolean; concerts: Concert[]; error: string | null; empty: boolean };

export function useNearby(place: Place | null): NearbyState {
  const [result, setResult] = useState<NearbyResult | null>(null);

  useEffect(() => {
    if (!place) return;
    const controller = new AbortController();
    const { signal } = controller;
    findNearby(place, signal)
      .then((concerts) => setResult({ place, concerts, error: null }))
      .catch((caught: Error) => {
        if (signal.aborted) return;
        const unreachable = caught instanceof TypeError;
        const error = unreachable ? "Concert Scout's API is not responding." : caught.message;
        setResult({ place, concerts: [], error });
      });
    return () => controller.abort();
  }, [place]);

  // A result for an earlier place is stale, so the current place counts as still loading.
  const current = result?.place === place ? result : null;
  return {
    loading: Boolean(place) && !current,
    concerts: current?.concerts ?? [],
    error: current?.error ?? null,
    empty: current?.concerts.length === 0 && !current.error,
  };
}
