import { describe, expect, it } from "vitest";

import { formatVenueCharacter, venueKey } from "@/lib/venues";

describe("venueKey", () => {
  // Each case matches the API's `venues.venue_key`.
  it.each([
    ["The Bowery Ballroom", "New York", "bowery ballroom::new york"],
    ["Bowery  Ballroom", "new york", "bowery ballroom::new york"],
    ["Red Rocks Amphitheatre", undefined, "red rocks amphitheatre"],
    ["Red Rocks Amphitheatre", "   ", "red rocks amphitheatre"],
    ["Café du Nord", "San Francisco", "cafe du nord::san francisco"],
    ["9:30 Club", "Washington", "930 club::washington"],
  ])("reads (%j, %j) as %j", (name, city, key) => {
    expect(venueKey(name, city)).toBe(key);
  });
});

describe("formatVenueCharacter", () => {
  it("formats tier and comma-separated capacity for verified rooms", () => {
    expect(
      formatVenueCharacter({
        name: "Bowery Ballroom",
        city: "New York",
        capacity: 575,
        tier: "Club / Ballroom",
        venue_type: "Music venue",
      }),
    ).toBe("Club / Ballroom · 575 cap");

    expect(
      formatVenueCharacter({
        name: "Madison Square Garden",
        city: "New York",
        capacity: 19500,
        tier: "Arena / Stadium",
      }),
    ).toBe("Arena / Stadium · 19,500 cap");
  });

  it("falls back to verified venue type when capacity is absent", () => {
    expect(
      formatVenueCharacter({
        name: "The Independent",
        city: "San Francisco",
        venue_type: "Music venue",
      }),
    ).toBe("Music venue");
  });

  it("returns null for unverified venues so only the venue name shows", () => {
    expect(formatVenueCharacter({ name: "Unknown Hall", city: "Oakland" })).toBeNull();
  });
});
