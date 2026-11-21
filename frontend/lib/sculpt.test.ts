import { describe, expect, it } from "vitest";

import {
  DEFAULT_SCULPT,
  isBoosted,
  isDefaultSculpt,
  MAX_BOOST_ARTISTS,
  MAX_EXCLUDE_ARTISTS,
  relaxFilter,
  removeSteeringArtist,
  toggleBoostArtist,
  toggleExcludeArtist,
} from "./sculpt";

describe("sculpt state helpers", () => {
  it("recognizes default state vs modified dials", () => {
    expect(isDefaultSculpt(DEFAULT_SCULPT)).toBe(true);
    expect(
      isDefaultSculpt({ ...DEFAULT_SCULPT, discovery: "deep_cuts" }),
    ).toBe(false);
    expect(isDefaultSculpt({ ...DEFAULT_SCULPT, max_price: 40 })).toBe(false);
    expect(isDefaultSculpt({ ...DEFAULT_SCULPT, weekends_only: true })).toBe(
      false,
    );
    expect(isDefaultSculpt({ ...DEFAULT_SCULPT, intimate_only: true })).toBe(
      false,
    );
    expect(isDefaultSculpt({ ...DEFAULT_SCULPT, hide_festivals: true })).toBe(
      false,
    );
  });

  it("toggles boost and exclude artists mutually exclusively within bounds", () => {
    let state = toggleBoostArtist(DEFAULT_SCULPT, "Khruangbin");
    expect(state.boost_artists).toEqual(["Khruangbin"]);
    expect(isBoosted(state, "khruangbin")).toBe(true);

    // Excluding a boosted artist moves it out of boost_artists.
    state = toggleExcludeArtist(state, "Khruangbin");
    expect(state.boost_artists).toEqual([]);
    expect(state.exclude_artists).toEqual(["Khruangbin"]);

    // Boosting again moves it back and removes from exclude_artists.
    state = toggleBoostArtist(state, "khruangbin");
    expect(state.boost_artists).toEqual(["khruangbin"]);
    expect(state.exclude_artists).toEqual([]);

    // Toggling the same artist removes it.
    state = toggleBoostArtist(state, "Khruangbin");
    expect(state.boost_artists).toEqual([]);

    // Caps boost at MAX_BOOST_ARTISTS and exclude at MAX_EXCLUDE_ARTISTS.
    let boosted = DEFAULT_SCULPT;
    for (let i = 0; i < MAX_BOOST_ARTISTS + 3; i++) {
      boosted = toggleBoostArtist(boosted, `Artist ${i}`);
    }
    expect(boosted.boost_artists).toHaveLength(MAX_BOOST_ARTISTS);

    let excluded = DEFAULT_SCULPT;
    for (let i = 0; i < MAX_EXCLUDE_ARTISTS + 3; i++) {
      excluded = toggleExcludeArtist(excluded, `Excluded ${i}`);
    }
    expect(excluded.exclude_artists).toHaveLength(MAX_EXCLUDE_ARTISTS);
  });

  it("removes individual steering artists cleanly", () => {
    let state = toggleBoostArtist(DEFAULT_SCULPT, "Bonobo");
    state = toggleExcludeArtist(state, "Skream");
    state = removeSteeringArtist(state, "boost", "bonobo");
    expect(state.boost_artists).toEqual([]);
    expect(state.exclude_artists).toEqual(["Skream"]);
    state = removeSteeringArtist(state, "exclude", "skream");
    expect(isDefaultSculpt(state)).toBe(true);
  });

  it("relaxes the specific filter that eliminated all picks", () => {
    const priced = relaxFilter(
      { ...DEFAULT_SCULPT, max_price: 40, weekends_only: true },
      "max_price",
    );
    expect(priced.next.max_price).toBeNull();
    expect(priced.next.weekends_only).toBe(true);
    expect(priced.reason).toMatch(/\$40/);
    expect(priced.label).toBe("Remove price cap");

    const wknd = relaxFilter(
      { ...DEFAULT_SCULPT, weekends_only: true },
      "weekends_only",
    );
    expect(wknd.next.weekends_only).toBe(false);
    expect(wknd.label).toBe("Show any day");

    const room = relaxFilter(
      { ...DEFAULT_SCULPT, intimate_only: true },
      "intimate_only",
    );
    expect(room.next.intimate_only).toBe(false);
    expect(room.label).toBe("Show any room size");

    const fest = relaxFilter(
      { ...DEFAULT_SCULPT, hide_festivals: true },
      "hide_festivals",
    );
    expect(fest.next.hide_festivals).toBe(false);
    expect(fest.label).toBe("Include festivals");

    const excl = relaxFilter(
      { ...DEFAULT_SCULPT, exclude_artists: ["Artist A"] },
      "exclude_artists",
    );
    expect(excl.next.exclude_artists).toEqual([]);
    expect(excl.label).toBe("Clear hidden Artists");

    const fallback = relaxFilter(
      { ...DEFAULT_SCULPT, discovery: "deep_cuts" },
      null,
    );
    expect(isDefaultSculpt(fallback.next)).toBe(true);
    expect(fallback.label).toBe("Reset filters");
  });
});
