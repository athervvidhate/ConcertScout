import { useSyncExternalStore } from "react";

import { API_URL, refusal } from "@/lib/search";

const TASTE_KEY = "concert-scout-taste";

export type UsernameSource = "lastfm" | "listenbrainz";
export type FileTasteSource = "exportify" | "tunemymusic" | "csv" | "history";
export type TasteSource = UsernameSource | FileTasteSource | "seed" | "youtube" | "list";

export const SOURCE_NAMES: Record<TasteSource, string> = {
  seed: "your Taste picks",
  csv: "your CSV file",
  exportify: "your Exportify CSV file",
  tunemymusic: "your TuneMyMusic file",
  youtube: "your YouTube playlist",
  lastfm: "Last.fm",
  listenbrainz: "ListenBrainz",
  history: "your Spotify history file",
  list: "your list",
};

export function isFileTasteSource(source: TasteSource): source is FileTasteSource {
  return (
    source === "exportify" ||
    source === "tunemymusic" ||
    source === "csv" ||
    source === "history"
  );
}

// A Taste brought in from elsewhere: Artist names, favourites first, and the sources they came
// from, newest first. It lives on this device, and on a signed-in Account too.
export type ImportedTaste = {
  sources: TasteSource[];
  artists: string[];
  importedAt?: string;
};

function artistKey(name: string): string {
  return name.trim().replace(/\s+/g, " ").toLowerCase();
}

/** Each Artist once, in the order given. */
function distinctArtists(names: string[]): string[] {
  const seen = new Set<string>();
  return names.filter((name) => {
    const key = artistKey(name);
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/**
 * The Taste with a source's Artists added. The new list and the old take turns, the new one first,
 * so a long playlist cannot push hand-picked Artists past what a Search reads.
 */
export function combineTaste(
  current: ImportedTaste | null,
  source: TasteSource,
  artists: string[],
): ImportedTaste {
  const importedAt = new Date().toISOString();
  if (!current) return { sources: [source], artists: distinctArtists(artists), importedAt };
  const turns: string[] = [];
  for (let i = 0; i < Math.max(artists.length, current.artists.length); i++) {
    if (i < artists.length) turns.push(artists[i]);
    if (i < current.artists.length) turns.push(current.artists[i]);
  }
  return {
    sources: [source, ...current.sources.filter((kept) => kept !== source)],
    artists: distinctArtists(turns),
    importedAt,
  };
}

/** "your Taste picks and your YouTube playlist". */
export function describeSources(sources: TasteSource[]): string {
  const names = sources.map((source) => SOURCE_NAMES[source]);
  if (names.length < 3) return names.join(" and ");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

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

export async function fetchYouTubePlaylistTaste(url: string): Promise<string[]> {
  const response = await fetch(`${API_URL}/taste/youtube-playlist`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  if (!response.ok) throw await refusal(response);
  const { artists }: { artists: string[] } = await response.json();
  return artists;
}

export async function fetchArtistSuggestions(
  query: string,
  signal?: AbortSignal,
): Promise<string[]> {
  const params = new URLSearchParams({ q: query });
  const response = await fetch(`${API_URL}/artists/suggest?${params}`, { signal });
  if (!response.ok) throw await refusal(response);
  const { artists }: { artists: string[] } = await response.json();
  return artists;
}

export async function fetchRelatedArtists(
  names: string[],
  signal?: AbortSignal,
): Promise<string[]> {
  const params = new URLSearchParams();
  for (const name of names) params.append("names", name);
  const response = await fetch(`${API_URL}/artists/related?${params}`, { signal });
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
    return Array.isArray(taste.artists) && Array.isArray(taste.sources) && taste.sources.length > 0
      ? taste
      : null;
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

/** The Taste on this device right now, for code that runs outside a render. */
export function readTaste(): ImportedTaste | null {
  return snapshot();
}

export function keepTaste(taste: ImportedTaste): void {
  const stamped: ImportedTaste = taste.importedAt
    ? taste
    : { ...taste, importedAt: new Date().toISOString() };
  localStorage.setItem(TASTE_KEY, JSON.stringify(stamped));
  listeners.forEach((listener) => listener());
}

/** Adds a source's Artists to the Taste on this device. */
export function addToTaste(source: TasteSource, artists: string[]): void {
  keepTaste(combineTaste(snapshot(), source, artists));
}

/** The Taste's whole list, as edited. A name the list did not have was picked by hand. */
export function replaceTasteArtists(artists: string[]): void {
  const current = snapshot();
  const known = new Set(current?.artists.map(artistKey));
  const picked = artists.some((name) => !known.has(artistKey(name)));
  const sources = current?.sources ?? [];
  keepTaste({
    sources: picked || sources.length === 0 ? ["seed", ...sources.filter((s) => s !== "seed")] : sources,
    artists: distinctArtists(artists),
    importedAt: new Date().toISOString(),
  });
}

export function forgetTaste(): void {
  localStorage.removeItem(TASTE_KEY);
  listeners.forEach((listener) => listener());
}

export function useImportedTaste(): ImportedTaste | null {
  return useSyncExternalStore(subscribe, snapshot, () => null);
}
