import { formatMonthDay, formatPosterHeading } from "@/lib/format";
import type { SharedPoster } from "@/lib/share";
import { nameOf as headliner } from "@/lib/lineup";

// What a Shared Poster is about, from the Search's reading or else its first Artists.
export function sharedHeading({
  interpreted,
  recommendations,
}: Pick<SharedPoster, "interpreted" | "recommendations">): string {
  const reading = interpreted ? formatPosterHeading(interpreted) : "";
  const genres = interpreted?.genres.join(", ");
  if (reading && genres) return `${genres} · ${reading}`;
  return reading || genres || recommendations.slice(0, 3).map(headliner).join(", ");
}

// The link's title wherever it is shown: a browser tab, a chat preview, the share sheet.
export function sharedTitle(shared: Pick<SharedPoster, "interpreted" | "recommendations">): string {
  return `${sharedHeading(shared)} · Shared Poster`;
}

export function sharedSummary({ recommendations }: SharedPoster): string {
  const names = recommendations.map(headliner);
  if (!names.length) return "Its Concerts have passed. Start your own Search on Concert Scout.";
  const shown = names.slice(0, 4).join(", ");
  const more = names.length > 4 ? ` and ${names.length - 4} more` : "";
  const count = names.length === 1 ? "1 Concert" : `${names.length} Concerts`;
  return `${count} worth going out for: ${shown}${more}.`;
}

export function formatMade(made: string): string {
  return `${formatMonthDay(made)}, ${made.slice(0, 4)}`;
}
