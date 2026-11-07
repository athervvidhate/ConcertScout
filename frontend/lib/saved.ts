import { useMemo, useSyncExternalStore } from "react";

import { dateIn, viewerZone } from "@/lib/format";
import type { Recommendation } from "@/lib/search";

const SAVED_KEY = "concert-scout-saved";
const SKIPPED_KEY = "concert-scout-skipped";
const EMPTY = "[]";

export type Decision = "saved" | "skipped";

const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

function parseList<T>(raw: string): T[] {
  try {
    const list: unknown = JSON.parse(raw);
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

function readList<T>(key: string): T[] {
  return parseList(localStorage.getItem(key) ?? EMPTY);
}

function write(saved: Recommendation[], skipped: string[]) {
  localStorage.setItem(SAVED_KEY, JSON.stringify(saved));
  localStorage.setItem(SKIPPED_KEY, JSON.stringify(skipped));
  listeners.forEach((listener) => listener());
}

// Each write throws when the browser refuses storage, so no caller claims a save that failed.
export function saveConcert(recommendation: Recommendation): void {
  const id = recommendation.concert.id;
  const others = readList<Recommendation>(SAVED_KEY).filter((r) => r.concert.id !== id);
  const skipped = readList<string>(SKIPPED_KEY).filter((skippedId) => skippedId !== id);
  write([...others, recommendation], skipped);
}

export function skipConcert(id: string): void {
  const saved = readList<Recommendation>(SAVED_KEY).filter((r) => r.concert.id !== id);
  const skipped = readList<string>(SKIPPED_KEY).filter((skippedId) => skippedId !== id);
  write(saved, [...skipped, id]);
}

export function removeSaved(id: string): void {
  const saved = readList<Recommendation>(SAVED_KEY).filter((r) => r.concert.id !== id);
  write(saved, readList<string>(SKIPPED_KEY));
}

function useStored(key: string): string {
  return useSyncExternalStore(
    subscribe,
    () => localStorage.getItem(key) ?? EMPTY,
    () => EMPTY,
  );
}

export function useSavedConcerts(): Recommendation[] {
  const raw = useStored(SAVED_KEY);
  return useMemo(() => parseList<Recommendation>(raw), [raw]);
}

export function useDecisions(): Record<string, Decision> {
  const saved = useSavedConcerts();
  const rawSkipped = useStored(SKIPPED_KEY);
  return useMemo(() => {
    const skipped = parseList<string>(rawSkipped).map((id) => [id, "skipped" as const]);
    const kept = saved.map((r) => [r.concert.id, "saved" as const]);
    return Object.fromEntries([...skipped, ...kept]);
  }, [saved, rawSkipped]);
}

/** A Concert with no known date stays, because it may still be ahead. */
export function upcoming(saved: Recommendation[], now: Date): Recommendation[] {
  return saved.filter(({ concert }) => !concert.date || concert.date >= dateIn(concert.time_zone ?? viewerZone(), now));
}
