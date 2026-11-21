import { describe, expect, it } from "vitest";

import {
  canSaveReading,
  cleanReading,
  isSearchSaved,
  summarizeReading,
  type SavedSearch,
} from "./saved-searches";
import type { Reading } from "./search";

describe("saved searches helpers", () => {
  it("strips device location labels and extra fields from a Reading", () => {
    const dirty = {
      artists: ["Khruangbin"],
      descriptors: ["dreamy guitar"],
      tags: ["psychedelic"],
      genres: ["Rock"],
      place: "Near you",
      radius_miles: 50,
      region: "Local",
      lat: 41.88,
      lon: -87.63,
      taste: ["Secret"],
    } as unknown as Reading;

    const cleaned = cleanReading(dirty);
    expect(cleaned).toEqual({
      artists: ["Khruangbin"],
      descriptors: ["dreamy guitar"],
      tags: ["psychedelic"],
      genres: ["Rock"],
    });
    expect("place" in cleaned).toBe(false);
    expect("lat" in cleaned).toBe(false);
    expect("taste" in cleaned).toBe(false);
  });

  it("requires an Artist or named place to save a Search", () => {
    expect(canSaveReading(null)).toBe(false);
    expect(canSaveReading({ artists: [], genres: [], place: "Near you" })).toBe(false);
    expect(canSaveReading({ artists: [], descriptors: ["ambient"], genres: [] })).toBe(false);
    expect(canSaveReading({ artists: ["Khruangbin"], genres: [] })).toBe(true);
    expect(canSaveReading({ artists: [], genres: [], place: "Chicago" })).toBe(true);
  });

  it("matches an already-saved Search case-insensitively on query text and canonical Reading", () => {
    const existing: SavedSearch[] = [
      {
        id: "11111111-1111-1111-1111-111111111111",
        query_text: "Khruangbin in Chicago",
        reading: { artists: ["Khruangbin"], genres: [], place: "Chicago" },
        created_at: "2026-11-21T00:00:00Z",
      },
    ];
    expect(
      isSearchSaved(existing, "  khruangbin in chicago ", {
        artists: ["Khruangbin"],
        genres: [],
        place: "Chicago",
      }),
    ).toBe(true);
    expect(
      isSearchSaved(existing, "Khruangbin in Austin", {
        artists: ["Khruangbin"],
        genres: [],
        place: "Austin",
      }),
    ).toBe(false);
  });

  it("summarizes a Reading into crisp copy for the Account page", () => {
    expect(
      summarizeReading({
        artists: ["Khruangbin"],
        descriptors: ["psychedelic funk"],
        genres: ["Rock"],
        place: "Los Angeles",
        region: "Southern California",
        radius_miles: 100,
        start: "2026-12-01",
      }),
    ).toContain("Khruangbin · psychedelic funk · Southern California · From ");
  });
});
