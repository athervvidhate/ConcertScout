import { nameOf } from "@/lib/lineup";
import type { Reading, Recommendation, Unanswerable } from "@/lib/search";

export const MAX_REFINEMENT_CHARS = 300;
export const MAX_POSTER_ARTISTS = 20;

export type RefinementEntry = {
  id: string;
  text: string;
  label: string;
  reading: Reading;
};

export type UnanswerableNote = Unanswerable & {
  text: string;
};

const WEEKDAY_PLURALS = [
  "Mondays",
  "Tuesdays",
  "Wednesdays",
  "Thursdays",
  "Fridays",
  "Saturdays",
  "Sundays",
] as const;

const WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;

/** Ordered unique Artist names on the current Poster, capped to the API bound. */
export function posterArtistNames(recommendations: Recommendation[]): string[] {
  const seen = new Set<string>();
  const names: string[] = [];
  for (const rec of recommendations) {
    const name = nameOf(rec).trim();
    const key = name.toLocaleLowerCase();
    if (!name || seen.has(key)) continue;
    seen.add(key);
    names.push(name);
    if (names.length >= MAX_POSTER_ARTISTS) break;
  }
  return names;
}

/** Resolve a source ticket link for an unanswerable Refinement strictly from source records. */
export function findSourceForNote(
  note: UnanswerableNote,
  recommendations: Recommendation[],
): { url: string; label: string } | null {
  if (note.source_url) {
    return {
      url: note.source_url,
      label: note.source_label ?? note.artist ?? "ticket page",
    };
  }
  if (note.artist) {
    const target = note.artist.trim().toLocaleLowerCase();
    const match = recommendations.find(
      (r) =>
        nameOf(r).trim().toLocaleLowerCase() === target ||
        r.concert.artists.some((a) => a.name.trim().toLocaleLowerCase() === target),
    );
    if (match?.concert.url) {
      return { url: match.concert.url, label: nameOf(match) };
    }
  }
  const first = recommendations.find((r) => r.concert.url);
  if (first) {
    return { url: first.concert.url, label: nameOf(first) };
  }
  return null;
}

/** Plan what to restore when undoing a Refinement chip at `index`. */
export function planUndo(
  trail: RefinementEntry[],
  index: number,
  baseReading: Reading,
): { nextTrail: RefinementEntry[]; restoreReading: Reading; replayText?: string } {
  if (index < 0 || index >= trail.length) {
    return { nextTrail: trail, restoreReading: baseReading };
  }
  const before = trail.slice(0, index);
  const after = trail.slice(index + 1);
  const restoreReading =
    before.length > 0 ? before[before.length - 1].reading : baseReading;
  if (after.length === 0) {
    return { nextTrail: before, restoreReading };
  }
  return {
    nextTrail: before,
    restoreReading,
    replayText: after.map((entry) => entry.text).join(", "),
  };
}

/** Human-readable label for Reading `weekdays` (Monday=0 .. Sunday=6). */
export function formatWeekdays(weekdays: number[]): string {
  const unique = [...new Set(weekdays.filter((d) => d >= 0 && d <= 6))].sort(
    (a, b) => a - b,
  );
  if (unique.length === 0) return "";
  if (
    unique.length === 3 &&
    unique[0] === 4 &&
    unique[1] === 5 &&
    unique[2] === 6
  ) {
    return "Weekends";
  }
  if (unique.length === 1) {
    return WEEKDAY_PLURALS[unique[0]];
  }
  return unique.map((d) => WEEKDAY_SHORT[d]).join(", ");
}
