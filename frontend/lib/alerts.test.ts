import { describe, expect, it } from "vitest";

import { artistKey } from "@/lib/alerts";

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
