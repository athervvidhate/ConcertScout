import { expect, test } from "vitest";

import type { Concert } from "@/lib/search";
import type { SharedPoster } from "@/lib/share";
import { formatMade, sharedHeading, sharedSummary } from "@/lib/shared-heading";

const concert = (artist: string): Concert => ({
  id: artist,
  name: `${artist} Live`,
  url: "https://tickets.example",
  artists: [{ name: artist }],
});
const poster = (artists: string[], interpreted?: SharedPoster["interpreted"]): SharedPoster => ({
  made: "2026-11-09",
  interpreted,
  recommendations: artists.map((artist) => ({ concert: concert(artist) })),
});

test("a Shared Poster is named by its reading, else by its first Artists", () => {
  const reading = { place: "Chicago, IL", genres: ["dream pop"], artists: [] };
  expect(sharedHeading(poster(["A"], reading))).toBe("dream pop · Chicago, IL");
  expect(sharedHeading(poster(["A", "B", "C", "D"]))).toBe("A, B, C");
});

test("the preview summary names four Artists and counts the rest", () => {
  expect(sharedSummary(poster(["A", "B", "C", "D", "E", "F"]))).toBe(
    "6 Concerts worth going out for: A, B, C, D and 2 more.",
  );
  expect(sharedSummary(poster([]))).toContain("have passed");
});

test("the made date reads without a weekday or a shifted day", () => {
  expect(formatMade("2026-11-09")).toBe("Nov 9, 2026");
});
