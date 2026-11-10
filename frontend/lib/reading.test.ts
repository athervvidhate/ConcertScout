import { describe, expect, it } from "vitest";

import { anywhere, corrected, draftOf, overNextMonths } from "@/lib/reading";
import type { Reading } from "@/lib/search";

const SOCAL: Reading = {
  artists: ["Calvin Harris"],
  descriptors: ["house"],
  tags: ["house", "electro house"],
  genres: ["Dance/Electronic"],
  place: "Los Angeles, California, United States",
  region: "Southern California",
  radius_miles: 150,
  start: "2027-05-01",
  end: "2027-05-31",
};

describe("corrected", () => {
  it("asks for exactly the Reading it was given when nothing changed", () => {
    expect(corrected(SOCAL, draftOf(SOCAL))).toEqual(SOCAL);
  });

  it("drops a Region and its reach once the place is changed", () => {
    const reading = corrected(SOCAL, { ...draftOf(SOCAL), place: " Portland, Maine " });
    expect(reading.place).toBe("Portland, Maine");
    expect(reading).not.toHaveProperty("region");
    expect(reading).not.toHaveProperty("radius_miles");
  });

  it("leaves out a cleared place and blank dates instead of inventing them", () => {
    const reading = corrected(SOCAL, { ...draftOf(SOCAL), place: "", start: "", end: "" });
    expect(reading).not.toHaveProperty("place");
    expect(reading).not.toHaveProperty("start");
    expect(reading).not.toHaveProperty("end");
  });

  it("keeps an open-ended date range open", () => {
    const reading = corrected(SOCAL, { ...draftOf(SOCAL), start: "" });
    expect(reading).not.toHaveProperty("start");
    expect(reading.end).toBe("2027-05-31");
  });

  it("trims Artists and drops blank and repeated ones", () => {
    const artists = [" Disclosure ", "", "Calvin Harris", "Calvin Harris"];
    expect(corrected(SOCAL, { ...draftOf(SOCAL), artists }).artists).toEqual([
      "Disclosure",
      "Calvin Harris",
    ]);
  });

  it("removes the sound with the tags behind it", () => {
    const reading = corrected(SOCAL, { ...draftOf(SOCAL), sound: false });
    expect([reading.genres, reading.tags, reading.descriptors]).toEqual([[], [], []]);
  });
});

describe("reruns from the Poster", () => {
  it("widens to the next three months, ending on a real day", () => {
    expect(overNextMonths(SOCAL, "2026-11-30")).toMatchObject({ start: "2026-11-30", end: "2027-02-28" });
  });

  it("searches anywhere without a place, Region or reach", () => {
    const reading = anywhere(SOCAL);
    expect(reading).not.toHaveProperty("place");
    expect(reading).not.toHaveProperty("region");
    expect(reading).not.toHaveProperty("radius_miles");
    expect(reading.artists).toEqual(["Calvin Harris"]);
  });
});
