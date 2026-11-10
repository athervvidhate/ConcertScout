import type { Concert, Recommendation } from "@/lib/search";

/** The Artist who stands for a Concert. A festival has none, because its own name says what it is. */
export function headlinerOf(concert: Concert): string | undefined {
  return concert.festival ? undefined : concert.artists[0]?.name;
}

/** What a Recommendation is called: its headliner, or else the Concert's own name, never a guess. */
export function nameOf({ concert }: Recommendation): string {
  return headlinerOf(concert) ?? concert.name;
}

/** Who Listen plays: the headliner, or the festival Artist who best suits the Search. */
export function listenTo({ concert, lineup_match }: Recommendation): string | undefined {
  return headlinerOf(concert) ?? lineup_match?.[0];
}

const BILLED_MATCHES = 2;

/** A festival card's short line: who on its Lineup suits the Search, from the source's names. */
export function matchLine({ concert, lineup_match: matched = [] }: Recommendation): string | null {
  if (!concert.festival || !matched.length) return null;
  const shown = matched.slice(0, BILLED_MATCHES);
  const more = matched.length - shown.length;
  const names = more ? [...shown, `${more} more`] : shown;
  const listed = names.length > 1 ? `${names.slice(0, -1).join(", ")} and ${names.at(-1)}` : names[0];
  return `With ${listed} you might like`;
}
