import { describe, expect, it } from "vitest";

import { combineTaste, describeSources, type ImportedTaste } from "@/lib/taste";

const picks: ImportedTaste = { sources: ["seed"], artists: ["Khruangbin", "Bonobo", "Tame Impala"] };

describe("adding a source to a Taste", () => {
  it("starts a Taste from the first source", () => {
    const taste = combineTaste(null, "youtube", ["Four Tet", "four tet ", "Caribou"]);
    expect(taste.sources).toEqual(["youtube"]);
    expect(taste.artists).toEqual(["Four Tet", "Caribou"]);
  });

  it("takes turns with the Taste it joins, the new source first and each Artist once", () => {
    const taste = combineTaste(picks, "youtube", ["Four Tet", "bonobo", "Caribou", "Jamie xx"]);
    expect(taste.sources).toEqual(["youtube", "seed"]);
    expect(taste.artists).toEqual([
      "Four Tet",
      "Khruangbin",
      "bonobo",
      "Caribou",
      "Tame Impala",
      "Jamie xx",
    ]);
  });

  it("keeps hand picks near the top beside a long playlist", () => {
    const playlist = Array.from({ length: 50 }, (_, i) => `Artist ${i}`);
    const taste = combineTaste(picks, "youtube", playlist);
    expect(taste.artists.slice(0, 6)).toEqual(["Artist 0", "Khruangbin", "Artist 1", "Bonobo", "Artist 2", "Tame Impala"]);
    expect(taste.artists).toHaveLength(53);
  });

  it("moves a source that comes again to the front instead of naming it twice", () => {
    const both = combineTaste(picks, "youtube", ["Four Tet"]);
    expect(combineTaste(both, "seed", ["Caribou"]).sources).toEqual(["seed", "youtube"]);
  });
});

describe("naming a Taste's sources", () => {
  it("joins them in plain words", () => {
    expect(describeSources(["seed"])).toBe("your Taste picks");
    expect(describeSources(["youtube", "seed"])).toBe("your YouTube playlist and your Taste picks");
    expect(describeSources(["youtube", "seed", "lastfm"])).toBe(
      "your YouTube playlist, your Taste picks and Last.fm",
    );
  });
});
