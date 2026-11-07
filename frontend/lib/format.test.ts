import { describe, expect, it } from "vitest";

import { formatDate, formatPosterHeading, formatPrice, formatTime } from "@/lib/format";

describe("formatDate", () => {
  it("keeps the venue's calendar day", () => {
    expect(formatDate("2026-11-20")).toBe("Fri, Nov 20, 2026");
  });
});

describe("formatTime", () => {
  it("keeps the venue's local time", () => {
    expect(formatTime("19:30:00")).toBe("7:30 PM");
  });
});

describe("formatPrice", () => {
  it("shows a range in the source currency", () => {
    expect(formatPrice({ min: 45.5, max: 120, currency: "USD" })).toBe("$45.50 to $120.00");
  });

  it("shows one price when the range is a single value", () => {
    expect(formatPrice({ min: 30, max: 30, currency: "GBP" })).toBe("£30.00");
  });
});
describe("Search headings", () => {
  const read = { artists: [], genres: [] };

  it("names both years when a range crosses one", () => {
    expect(formatPosterHeading({ ...read, start: "2026-11-06", end: "2027-11-06" })).toBe(
      "Nov 6, 2026 to Nov 6, 2027",
    );
  });

  it("shows a region's own name, not its center", () => {
    const place = "Los Angeles, California, United States";
    expect(formatPosterHeading({ ...read, place, region: "Southern California" })).toBe(
      "Southern California",
    );
  });
});
