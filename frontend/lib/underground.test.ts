import { describe, expect, it } from "vitest";

import {
  hasUndergroundBadge,
  isSoldOut,
  undergroundSourceLabel,
} from "@/lib/underground";

describe("underground source and status labels", () => {
  it("maps underground venue calendars and curated Eventbrite promoters honestly", () => {
    expect(undergroundSourceLabel("venue_calendar")).toBe("Underground room");
    expect(undergroundSourceLabel("eventbrite")).toBe("Curated promoter");
    expect(undergroundSourceLabel("ticketmaster")).toBeNull();
    expect(undergroundSourceLabel("jambase")).toBeNull();
    expect(undergroundSourceLabel(undefined)).toBeNull();
  });

  it("reports sold out only when explicitly true", () => {
    expect(isSoldOut({ sold_out: true })).toBe(true);
    expect(isSoldOut({ sold_out: false })).toBe(false);
    expect(isSoldOut({})).toBe(false);
  });

  it("omits badges for standard listings without sold-out status", () => {
    expect(hasUndergroundBadge({ source: "ticketmaster" })).toBe(false);
    expect(hasUndergroundBadge({ source: "jambase", sold_out: false })).toBe(false);
    expect(hasUndergroundBadge({ source: "venue_calendar" })).toBe(true);
    expect(hasUndergroundBadge({ source: "eventbrite", sold_out: true })).toBe(true);
    expect(hasUndergroundBadge({ source: "ticketmaster", sold_out: true })).toBe(true);
  });
});
