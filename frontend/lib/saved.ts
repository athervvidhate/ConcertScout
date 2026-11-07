import type { Recommendation } from "@/lib/search";

const KEY = "concert-scout-saved";

export function readSaved(): Recommendation[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "[]");
  } catch {
    return [];
  }
}

// Throws when the browser refuses storage, so the caller never claims a save that did not happen.
export function saveConcert(recommendation: Recommendation): void {
  const others = readSaved().filter((r) => r.concert.id !== recommendation.concert.id);
  localStorage.setItem(KEY, JSON.stringify([...others, recommendation]));
}
