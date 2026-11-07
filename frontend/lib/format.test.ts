import { describe, expect, it } from "vitest";

import { byVenue, dateIn, formatConcertTime, formatDate, formatPosterHeading, formatPrice, formatTime, presaleLine } from "@/lib/format";

describe("formatDate", () => {
  it("keeps the venue's calendar day", () => {
    expect(formatDate("2026-11-20")).toBe("Fri, Nov 20, 2026");
  });
});

describe("presaleLine", () => {
  const concert = { id: "one", name: "One", url: "https://tickets.example", artists: [] };
  const opens = new Date(2027, 0, 13, 10, 0);
  const closes = new Date(2027, 0, 14, 10, 0);
  const presale = { name: "Artist Presale", start: opens.toISOString(), end: closes.toISOString() };
  const sale = { ...concert, general_sale: new Date(2027, 0, 15, 10, 0).toISOString(), presales: [presale] };

  it("gives the start of a presale still to come", () => {
    expect(presaleLine(sale, new Date(2027, 0, 1))).toBe("Artist Presale starts Jan 13, 10:00 AM");
  });

  it("says when a presale is running", () => {
    expect(presaleLine(sale, new Date(2027, 0, 13, 12))).toBe("Artist Presale on now");
  });

  it("shows the soonest presale that has not ended", () => {
    const later = { name: "Live Nation Presale", start: closes.toISOString(), end: new Date(2027, 0, 14, 22).toISOString() };
    expect(presaleLine({ ...sale, presales: [later, presale] }, new Date(2027, 0, 1))).toContain("Artist Presale");
    expect(presaleLine({ ...sale, presales: [later, presale] }, new Date(2027, 0, 14, 11))).toContain("Live Nation Presale");
  });

  it("shows nothing once general sale has begun or every presale has ended", () => {
    expect(presaleLine(sale, new Date(2027, 0, 16))).toBeNull();
    expect(presaleLine({ ...sale, general_sale: undefined }, new Date(2027, 0, 14, 11))).toBeNull();
    expect(presaleLine(concert, new Date(2027, 0, 1))).toBeNull();
  });
});

describe("byVenue", () => {
  const show = (id: string, venue: string, date: string) => ({
    id, name: id, url: "https://tickets.example", artists: [], venue, city: "San Diego", region: "CA", date,
  });

  it("gathers a venue's dates and keeps the order they came in", () => {
    const groups = byVenue([show("a", "Viejas", "2027-05-21"), show("b", "Forum", "2027-05-22"), show("c", "Viejas", "2027-05-23")]);
    expect(groups.map((group) => group.map(({ id }) => id))).toEqual([["a", "c"], ["b"]]);
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

describe("formatPrice", () => {
  it("drops empty cents and keeps real ones when compact", () => {
    expect(formatPrice({ min: 38, max: 38, currency: "USD" }, true)).toBe("$38");
    expect(formatPrice({ min: 38.3, max: 38.3, currency: "USD" }, true)).toBe("$38.30");
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

describe("formatConcertTime", () => {
  const show = { id: "one", name: "One", url: "https://tickets.example", artists: [], date: "2027-01-15", time: "19:30:00" };

  it("keeps the venue's clock and leaves the zone out when the visitor shares it", () => {
    expect(formatConcertTime({ ...show, time_zone: "America/Chicago" }, "America/Chicago")).toBe("7:30 PM");
  });

  it("treats two names for the same clock as one zone", () => {
    expect(formatConcertTime({ ...show, time_zone: "America/New_York" }, "America/Detroit")).toBe("7:30 PM");
  });

  it("names the venue's zone for a visitor somewhere else", () => {
    expect(formatConcertTime({ ...show, time_zone: "America/Chicago" }, "America/Los_Angeles")).toBe("7:30 PM CST");
    expect(formatConcertTime({ ...show, time_zone: "Europe/London" }, "America/Los_Angeles")).toBe("7:30 PM GMT");
  });

  it("reads the zone in force on the Concert's date", () => {
    expect(formatConcertTime({ ...show, date: "2027-07-15", time_zone: "America/Chicago" }, "UTC")).toBe("7:30 PM CDT");
  });

  it("invents nothing for a missing time or zone", () => {
    expect(formatConcertTime({ ...show, time: undefined, time_zone: "America/Chicago" }, "UTC")).toBeUndefined();
    expect(formatConcertTime(show, "UTC")).toBe("7:30 PM");
  });
});

describe("dateIn", () => {
  it("gives the calendar day in that zone", () => {
    const moment = new Date("2026-11-07T07:30:00Z");
    expect(dateIn("America/Los_Angeles", moment)).toBe("2026-11-06");
    expect(dateIn("America/New_York", moment)).toBe("2026-11-07");
  });
});
