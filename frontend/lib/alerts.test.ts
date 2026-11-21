import { describe, expect, it } from "vitest";

import { artistKey, defaultTimeZone, timeZoneOptions } from "@/lib/alerts";

describe("artistKey", () => {
  // Each pair is what the API's `names.normalize` returns, so the Follow button agrees with it.
  it.each([
    ["Contract  Artist", "contract artist"],
    ["Beyoncé", "beyonce"],
    ["Simon & Garfunkel", "simon and garfunkel"],
    ["AC/DC", "acdc"],
    ["!!!", "!!!"],
    ["Sigur Rós", "sigur ros"],
    ["Tyler, the Creator", "tyler the creator"],
    ["  Fred again..  ", "fred again"],
    ["The National", "national"],
  ])("reads %j as %j", (name, key) => {
    expect(artistKey(name)).toBe(key);
  });
});

describe("timeZoneOptions", () => {
  it("returns a sorted list that always includes the browser and saved time zones", () => {
    const options = timeZoneOptions("America/New_York", "America/Los_Angeles");
    expect(options).toContain("America/New_York");
    expect(options).toContain("America/Los_Angeles");
    expect(options).toContain("UTC");
    expect([...options].sort((a, b) => a.localeCompare(b))).toEqual(options);
  });

  it("returns a non-empty default time zone", () => {
    expect(defaultTimeZone().length).toBeGreaterThan(0);
  });
});
