import { describe, expect, it } from "vitest";

import { formatDate, formatPrice, formatTime } from "@/lib/format";

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
