import type { Reading } from "@/lib/search";

// The API refuses dates past this many days ahead, in the visitor's own zone.
export const FURTHEST_DAYS = 400;

// What a person can change in a Reading. Blank fields mean "not set".
export type Draft = {
  artists: string[];
  place: string;
  start: string;
  end: string;
  // Sounds go together: the tags behind them are not tied to any one sound chip.
  sound: boolean;
};

export function draftOf(reading: Reading): Draft {
  return {
    artists: [...reading.artists],
    place: reading.region ?? reading.place ?? "",
    start: reading.start ?? "",
    end: reading.end ?? "",
    sound: true,
  };
}

/** The Reading a corrected Draft asks for. A place left as it was keeps its Region and reach. */
export function corrected(reading: Reading, draft: Draft): Reading {
  const place = draft.place.trim();
  const kept = place === (reading.region ?? reading.place ?? "");
  return {
    artists: [...new Set(draft.artists.map((name) => name.trim()).filter(Boolean))],
    descriptors: draft.sound ? (reading.descriptors ?? []) : [],
    tags: draft.sound ? (reading.tags ?? []) : [],
    genres: draft.sound ? reading.genres : [],
    ...(kept
      ? { place: reading.place, region: reading.region, radius_miles: reading.radius_miles }
      : place
        ? { place }
        : {}),
    ...(draft.start ? { start: draft.start } : {}),
    ...(draft.end ? { end: draft.end } : {}),
  };
}

export function addDays(date: string, days: number): string {
  const day = new Date(`${date}T00:00:00Z`);
  day.setUTCDate(day.getUTCDate() + days);
  return day.toISOString().slice(0, 10);
}

function addMonths(date: string, months: number): string {
  const day = new Date(`${date}T00:00:00Z`);
  const target = day.getUTCMonth() + months;
  day.setUTCMonth(target);
  // Jan 31 plus a month is the last day of February, not March 3.
  if (day.getUTCMonth() !== ((target % 12) + 12) % 12) day.setUTCDate(0);
  return day.toISOString().slice(0, 10);
}

/** The same Search over the next three months. */
export function overNextMonths(reading: Reading, today: string): Reading {
  return { ...reading, start: today, end: addMonths(today, 3) };
}

/** The same Search anywhere, so a named Artist's Concerts elsewhere can show. */
export function anywhere(reading: Reading): Reading {
  const { artists, descriptors, tags, genres, start, end } = reading;
  return { artists, descriptors, tags, genres, start, end };
}
