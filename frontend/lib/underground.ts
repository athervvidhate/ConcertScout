import type { Concert } from "@/lib/search";

export type UndergroundSourceLabel = "Underground room" | "Curated promoter";

/** Honest source label for underground room and curated promoter Concerts; null for standard feeds. */
export function undergroundSourceLabel(
  source?: Concert["source"],
): UndergroundSourceLabel | null {
  if (source === "venue_calendar") return "Underground room";
  if (source === "eventbrite") return "Curated promoter";
  return null;
}

/** True only when the source explicitly reported sold-out availability. */
export function isSoldOut(concert: Pick<Concert, "sold_out">): boolean {
  return concert.sold_out === true;
}

/** Whether a Concert carries any underground source or sold-out badge. */
export function hasUndergroundBadge(
  concert: Pick<Concert, "source" | "sold_out">,
): boolean {
  return undergroundSourceLabel(concert.source) !== null || isSoldOut(concert);
}
