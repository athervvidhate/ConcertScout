import type { Concert } from "@/lib/search";

const SEPARATOR = /\s+[-–—|/•·]\s+|\s*[:()[\]]\s*/u;
// Words that only connect a removed name to what is left.
const LEADING = /^(?:(?:presents?|featuring|feat\.?|ft\.?|starring|with|w\/|w\.|w|and|plus|&|\+|x|vs\.?|special guests?)(?:\s+|$))+/iu;
const TRAILING = /(?:\s+|^)(?:presents?|featuring|feat\.?|ft\.?|starring|with|w\/|w\.|w|and|plus|&|\+|x|vs\.?|in|at|of|by|for|live)$/iu;
// A credit that runs on past a removed name says who else is playing, not what the show is.
const CREDITS = /\s+(?:feat\.?|ft\.?|featuring|w\/|w\.|(?:with|\+|&|and) (?:very )?special guests?|\+ more).*$/iu;
const NOTICE = /^(?:moved to|rescheduled|new date|new venue|cancelled)\b/iu;
const SAY_NOTHING = new RegExp(
  "^(?:" +
    [
      "",
      "the",
      "an? (?:intimate )?(?:evening|night)",
      "live",
      "in concert",
      "concert",
      "music",
      "tickets?",
      "show",
      "(?:ages? )?\\d{1,2}\\+?(?: and (?:over|up))?(?: event| only)?",
      "all ages",
      "a|tba|b2b",
      "quartet|quintet|trio|band|orchestra|ensemble",
      "(?:the )?(?:(?:world|north american?|us|usa|uk|arena|stadium|headline|fall|spring|summer|winter|\\d{4})\\s+)*tour(?: \\d{4})?",
      "(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\\.?",
      "(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\\.? \\d{1,2}(?:st|nd|rd|th)?",
    ].join("|") +
    ")$",
  "iu",
);
// Bare punctuation left after a name comes out, like the "+" in "A + B".
const STRAY = /^[\s\p{Cf}&+,.;!?@'‘’*~|/•·–—-]+|[\s\p{Cf}&+,.;'‘’*~|/•·–—-]+$/gu;

function fold(text: string): string {
  return Array.from(text, (character) => character.normalize("NFD").replace(/\p{M}/gu, "")[0] ?? character).join("");
}

function pattern(name: string): RegExp {
  const words = fold(name).trim().split(/\s+/u).map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  return new RegExp(`(?<![\\p{L}\\p{N}])(?:the\\s+)?${words.join("\\s+")}(?:['’]s)?(?![\\p{L}\\p{N}])`, "giu");
}

// Longest first, so "Chris Brown Band" goes before "Chris Brown". The folded text keeps each
// character's position, so the original spelling stays in what remains.
function without(title: string, names: string[]): { rest: string; found: boolean } {
  const characters = Array.from(title);
  let folded = fold(title);
  let found = false;
  for (const name of [...names].sort((a, b) => b.length - a.length)) {
    if (!name.trim()) continue;
    folded = folded.replace(pattern(name), (match) => {
      found = true;
      return "\u0000".repeat(Array.from(match).length);
    });
  }
  const kept = Array.from(folded).map((character, index) => (character === "\u0000" ? " " : characters[index]));
  return { rest: kept.join("").replace(/\s+/gu, " ").trim(), found };
}

function same(a: string, b: string): boolean {
  const letters = (text: string) => fold(text).toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
  return letters(a) === letters(b);
}

function clean(piece: string): string {
  let text = piece.replace(CREDITS, "").replace(STRAY, "");
  for (let before = ""; before !== text; ) {
    before = text;
    text = text.replace(LEADING, "").replace(TRAILING, "").replace(STRAY, "");
  }
  return text;
}

/**
 * What a Concert's listing says beyond the Artist, such as its tour name, or nothing.
 * It only removes words from the source's title and never adds any.
 */
export function showTitle({ name, artists, venue, city, region }: Concert, shown: string): string | null {
  const billed = [shown, ...artists.map((artist) => artist.name)];
  const { rest, found } = without(name.replace(/["“”]/gu, ""), billed);
  if (!found) return SAY_NOTHING.test(name.trim()) || same(name, shown) ? null : name.trim();
  const place = without(rest, [venue ?? "", city ?? "", region ?? ""]).rest;
  const pieces = place
    .split(SEPARATOR)
    .map(clean)
    .filter((piece) => !SAY_NOTHING.test(piece) && !NOTICE.test(piece));
  return pieces.join(" - ") || null;
}
