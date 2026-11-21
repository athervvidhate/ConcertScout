import { useEffect, useSyncExternalStore } from "react";

import { accountFetch, currentAccount, subscribeAccount, useAccount } from "@/lib/account";
import { formatDate } from "@/lib/format";
import type { Reading } from "@/lib/search";

export const MAX_SAVED_SEARCHES = 5;

export type SavedSearch = {
  id: string;
  query_text: string;
  reading: Reading;
  last_run_at?: string | null;
  created_at: string;
};

/** Keeps only the canonical Reading fields shown to the person, never coordinates or Taste. */
export function cleanReading(reading: Reading): Reading {
  const cleaned: Reading = {
    artists: [...reading.artists],
    genres: [...reading.genres],
  };
  if (reading.descriptors?.length) cleaned.descriptors = [...reading.descriptors];
  if (reading.tags?.length) cleaned.tags = [...reading.tags];
  if (reading.place && reading.place.toLowerCase() !== "near you") cleaned.place = reading.place;
  if (cleaned.place && reading.radius_miles) cleaned.radius_miles = reading.radius_miles;
  if (cleaned.place && cleaned.radius_miles && reading.region) cleaned.region = reading.region;
  if (reading.start) cleaned.start = reading.start;
  if (reading.end) cleaned.end = reading.end;
  return cleaned;
}

/** A Saved Search needs an Artist or a named place, because device coordinates are never kept. */
export function canSaveReading(reading: Reading | null | undefined): boolean {
  if (!reading) return false;
  const cleaned = cleanReading(reading);
  return Boolean(cleaned.place || cleaned.artists.length > 0);
}

function canonicalKey(queryText: string, reading: Reading): string {
  const cleaned = cleanReading(reading);
  return JSON.stringify([
    queryText.trim().toLowerCase(),
    cleaned.artists,
    cleaned.descriptors ?? [],
    cleaned.tags ?? [],
    cleaned.genres,
    cleaned.place ?? null,
    cleaned.region ?? null,
    cleaned.radius_miles ?? null,
    cleaned.start ?? null,
    cleaned.end ?? null,
  ]);
}

export function isSearchSaved(
  saved: readonly SavedSearch[],
  queryText: string,
  reading: Reading,
): boolean {
  const target = canonicalKey(queryText, reading);
  return saved.some((item) => canonicalKey(item.query_text, item.reading) === target);
}

/** Plain summary of a Saved Search's Reading for the Account page. */
export function summarizeReading(reading: Reading): string {
  const parts: string[] = [];
  if (reading.artists.length > 0) parts.push(reading.artists.join(", "));
  const sound = reading.descriptors?.length ? reading.descriptors : reading.genres;
  if (sound.length > 0) parts.push(sound.join(", "));
  const where = reading.region ?? reading.place;
  if (where) parts.push(where);
  if (reading.start && reading.end) {
    parts.push(`${formatDate(reading.start)} to ${formatDate(reading.end)}`);
  } else if (reading.start) {
    parts.push(`From ${formatDate(reading.start)}`);
  } else if (reading.end) {
    parts.push(`Until ${formatDate(reading.end)}`);
  }
  return parts.join(" · ");
}

// The signed-in Account's Saved Searches, shared by Poster actions and the Account page.
let savedSearches: SavedSearch[] | null = null;
let owner: string | null = null;
let loading: Promise<void> | null = null;
const listeners = new Set<() => void>();

function set(next: SavedSearch[] | null) {
  savedSearches = next;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  const stop = subscribeAccount(() => {
    const account = currentAccount();
    const id = account.status === "signed-in" ? account.id : null;
    if (id !== owner) {
      owner = id;
      loading = null;
      set(null);
    }
  });
  return () => {
    listeners.delete(listener);
    stop();
  };
}

function load(): Promise<void> {
  loading ??= accountFetch("/saved-searches")
    .then((response) => response.json())
    .then((read: SavedSearch[]) => set(read))
    .catch((error) => {
      loading = null;
      throw error;
    });
  return loading;
}

/** The Account's Saved Searches once read, or null while loading or signed out. */
export function useSavedSearches(): SavedSearch[] | null {
  const account = useAccount();
  const id = account.status === "signed-in" ? account.id : null;
  const read = useSyncExternalStore(subscribe, () => savedSearches, () => null);
  useEffect(() => {
    if (!id) return;
    owner = id;
    void load().catch(() => {});
  }, [id]);
  return id ? read : null;
}

export async function reloadSavedSearches(): Promise<void> {
  loading = null;
  await load();
}

export async function saveSearch(queryText: string, reading: Reading): Promise<SavedSearch> {
  const cleaned = cleanReading(reading);
  const response = await accountFetch("/saved-searches", {
    method: "POST",
    body: JSON.stringify({ query_text: queryText.trim(), reading: cleaned }),
  });
  const created: SavedSearch = await response.json();
  const current = savedSearches ?? [];
  if (!current.some((item) => item.id === created.id)) {
    set([...current, created]);
  }
  return created;
}

export async function deleteSavedSearch(id: string): Promise<void> {
  await accountFetch(`/saved-searches/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (savedSearches) {
    set(savedSearches.filter((item) => item.id !== id));
  }
}
