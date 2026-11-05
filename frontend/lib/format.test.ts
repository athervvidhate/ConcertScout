import { describe, expect, it } from "vitest";

import { formatDate, formatInterpreted, formatPrice, formatTime } from "@/lib/format";

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

describe("formatInterpreted", () => {
  it("joins the place, dates and Artists", () => {
    expect(
      formatInterpreted({
        place: "Chicago",
        start: "2026-11-06",
        end: "2026-11-15",
        artists: ["Khruangbin"],
      }),
    ).toBe("Chicago · Fri, Nov 6, 2026 to Sun, Nov 15, 2026 · Khruangbin");
  });

  it("shows one date for a single day", () => {
    expect(formatInterpreted({ start: "2026-11-06", end: "2026-11-06", artists: [] })).toBe(
      "Fri, Nov 6, 2026",
    );
  });

  it("words an open-ended range", () => {
    expect(formatInterpreted({ start: "2026-11-06", artists: [] })).toBe("from Fri, Nov 6, 2026");
    expect(formatInterpreted({ end: "2026-11-15", artists: [] })).toBe("until Sun, Nov 15, 2026");
  });

  it("leaves out what the interpreter did not find", () => {
    expect(formatInterpreted({ place: "Chicago", artists: [] })).toBe("Chicago");
  });
});
