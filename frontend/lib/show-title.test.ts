import { expect, test } from "vitest";

import type { Concert } from "@/lib/search";
import { showTitle } from "@/lib/show-title";

function title(name: string, artists: string[], place: Partial<Concert> = {}) {
  const concert = { id: "1", url: "", name, artists: artists.map((artist) => ({ name: artist })), ...place };
  return showTitle(concert, artists[0] ?? name);
}

test.each([
  ["JOHN SUMMIT - CTRL ESCAPE TOUR", ["John Summit"], "CTRL ESCAPE TOUR"],
  ["TYLA - THE A*POP WORLD TOUR", ["Tyla"], "THE A*POP WORLD TOUR"],
  ["PlaqueBoyMax Presents Rising Star", ["PlaqueBoyMax"], "Rising Star"],
  ["The R&B Tour - Starring Usher Raymond & Chris Brown", ["Chris Brown", "Usher Raymond"], "The R&B Tour"],
  ["DIIV - ZIRP! The World", ["DIIV"], "ZIRP! The World"],
  ["Mark O'Connor's Appalachian Christmas", ["Mark O'Connor"], "Appalachian Christmas"],
  ["Beyoncé: Renaissance", ["Beyonce"], "Renaissance"],
  ["Jam For Good Presents The Lichy Nuts", ["Lichy Nuts"], "Jam For Good"],
  ["Sonderfest 2026 feat. Truman Sinclair, Tristan + more", ["Truman Sinclair"], "Sonderfest 2026"],
  ["January Blues Festival: KING KING", ["King King"], "January Blues Festival"],
  ["Danny Brown: Atrocity Exhibition 10 Year Anniversary Show", ["Danny Brown"], "Atrocity Exhibition 10 Year Anniversary Show"],
])("%s keeps only what the Artist's name doesn't say", (name, artists, expected) => {
  expect(title(name, artists)).toBe(expected);
});

test.each([
  ["Brent Faiyaz", ["Brent Faiyaz"]],
  ["2hollis (18 and Over)", ["2hollis"]],
  ["Mustard Plug - Ages 16+", ["Mustard Plug"]],
  ["Missio (17+ Event)", ["Missio"]],
  ["ARMNHMR (18+)- MOVED TO HOUSE OF BLUES ANAHEIM", ["ARMNHMR"]],
  ["An Intimate Evening With Tamar Braxton", ["Tamar Braxton"]],
  ["Beyoncé World Tour 2027", ["Beyoncé"]],
  ["Soft Machine", ["Soft Machine."]],
  ["KING NO ONE", ["King No-One"]],
  ["King Gizzard & The Lizard Wizard", ["King Gizzard and the Lizard Wizard"]],
  ["King Gizzard and the Lizard Wizard", ["King Gizzard & The Lizard Wizard"]],
  ["Great Lake Swimmers w. Colleen Brown", ["Great Lake Swimmers", "Colleen Brown"]],
])("%s says nothing past the Artist", (name, artists) => {
  expect(title(name, artists)).toBeNull();
});

test("a place the row already shows comes out of the title", () => {
  const place = { city: "Hawthorne", region: "NJ" };
  expect(title("Red Worship: The Witness Tour - Hawthorne, NJ", ["Red Worship"], place)).toBe("The Witness Tour");
});

test("a name inside a longer word stays", () => {
  expect(title("Lovers Rock Night", ["Love"])).toBe("Lovers Rock Night");
});

test("a venue name with punctuation is matched literally", () => {
  const place = { venue: "Knitting Factory - Boise (Main)" };
  expect(title("Pup at Knitting Factory - Boise (Main)", ["Pup"], place)).toBeNull();
});

test("a title with no billed Artist in it stays whole", () => {
  expect(title("Lollapalooza - Saturday", ["Tyler"])).toBe("Lollapalooza - Saturday");
});

test("nothing is ever added to the source's title", () => {
  const words = (text: string) => text.toLowerCase().split(/\W+/).filter(Boolean);
  const name = "Fantasia, Anthony Hamilton, & October London: The Love of Soul Tour";
  const result = title(name, ["Fantasia", "Anthony Hamilton"])!;
  expect(words(result).every((word) => words(name).includes(word))).toBe(true);
});
