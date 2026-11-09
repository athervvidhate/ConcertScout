import { useSyncExternalStore } from "react";

import { API_URL, refusal } from "@/lib/search";

const TASTE_KEY = "concert-scout-taste";

export type UsernameSource = "lastfm" | "listenbrainz";
export type TasteSource = UsernameSource | "history" | "list";

export const SOURCE_NAMES: Record<TasteSource, string> = {
  lastfm: "Last.fm",
  listenbrainz: "ListenBrainz",
  history: "your Spotify history file",
  list: "your list",
};

// A Taste brought in from elsewhere: Artist names, favourites first. It lives only on this device.
export type ImportedTaste = { source: TasteSource; artists: string[] };

export async function fetchTaste(source: UsernameSource, username: string): Promise<string[]> {
  const response = await fetch(`${API_URL}/taste/${source}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username }),
  });
  if (!response.ok) throw await refusal(response);
  const { artists }: { artists: string[] } = await response.json();
  return artists;
}

const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

function parse(raw: string | null): ImportedTaste | null {
  if (!raw) return null;
  try {
    const taste: ImportedTaste = JSON.parse(raw);
    return Array.isArray(taste.artists) ? taste : null;
  } catch {
    return null;
  }
}

// Parsing only when the stored text changes gives React a stable snapshot.
let cached: { raw: string | null; taste: ImportedTaste | null } = { raw: null, taste: null };

function snapshot(): ImportedTaste | null {
  const raw = localStorage.getItem(TASTE_KEY);
  if (raw !== cached.raw) cached = { raw, taste: parse(raw) };
  return cached.taste;
}

export function keepTaste(taste: ImportedTaste): void {
  localStorage.setItem(TASTE_KEY, JSON.stringify(taste));
  listeners.forEach((listener) => listener());
}

export function forgetTaste(): void {
  localStorage.removeItem(TASTE_KEY);
  listeners.forEach((listener) => listener());
}

export function useImportedTaste(): ImportedTaste | null {
  return useSyncExternalStore(subscribe, snapshot, () => null);
}
