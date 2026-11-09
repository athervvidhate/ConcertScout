import { formatMonthDay, formatPosterHeading } from "@/lib/format";
import type { SharedPoster } from "@/lib/share";
import type { Recommendation } from "@/lib/search";

// Server pages use these, so they cannot come from the Ticket's client module.
const headliner = ({ concert }: Recommendation) => concert.artists[0]?.name ?? concert.name;

// What a Shared Poster is about, from the Search's reading or else its first Artists.
export function sharedHeading({ interpreted, recommendations }: SharedPoster): string {
  const reading = interpreted ? formatPosterHeading(interpreted) : "";
  const genres = interpreted?.genres.join(", ");
  if (reading && genres) return `${genres} · ${reading}`;
  return reading || genres || recommendations.slice(0, 3).map(headliner).join(", ");
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
