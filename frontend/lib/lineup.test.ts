import { expect, test } from "vitest";

import { listenTo, matchLine, nameOf } from "@/lib/lineup";
import type { Concert, Recommendation } from "@/lib/search";

const countdown: Concert = {
  id: "countdown",
  name: "Insomniac Countdown",
  url: "https://tickets.example/countdown",
  artists: [{ name: "33 Below" }, { name: "Alesso" }, { name: "DJ Snake" }, { name: "Tchami" }],
  festival: true,
};

const pick = (lineup_match: string[], concert = countdown): Recommendation => ({ concert, lineup_match });

test("a festival is called by its own name, never its first Artist", () => {
  expect(nameOf(pick(["Alesso"]))).toBe("Insomniac Countdown");
  expect(nameOf(pick([], { ...countdown, festival: false }))).toBe("33 Below");
});

test("Listen plays the festival Artist who best suits the Search", () => {
  expect(listenTo(pick(["Alesso", "DJ Snake"]))).toBe("Alesso");
  expect(listenTo(pick([]))).toBeUndefined();
});

test("a festival card names its best matches and counts the rest", () => {
  expect(matchLine(pick(["Alesso"]))).toBe("With Alesso you might like");
  expect(matchLine(pick(["Alesso", "DJ Snake"]))).toBe("With Alesso and DJ Snake you might like");
  expect(matchLine(pick(["Alesso", "DJ Snake", "Tchami"]))).toBe(
    "With Alesso, DJ Snake and 1 more you might like",
  );
  expect(matchLine(pick([]))).toBeNull();
});
