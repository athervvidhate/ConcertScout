import { describe, expect, it } from "vitest";

import { calendarFile, calendarFileName } from "@/lib/calendar";
import type { Concert } from "@/lib/search";

const NOW = new Date("2026-11-09T18:00:00Z");

const concert: Concert = {
  id: "tm-1",
  name: "Khruangbin",
  url: "https://tickets.example/khruangbin",
  artists: [{ name: "Khruangbin" }],
  date: "2026-12-05",
  time: "19:30:00",
  time_zone: "America/Chicago",
  venue: "Riviera Theatre",
  city: "Chicago",
  region: "IL",
};

// Content lines are folded at 75 octets, so unfold before reading them.
function lines(file: string): string[] {
  return file.replace(/\r\n /g, "").split("\r\n").filter(Boolean);
}

describe("calendarFile", () => {
  it("writes a timed event on the venue's clock", () => {
    const file = lines(calendarFile(concert, NOW)!);
    expect(file).toContain("DTSTART;TZID=America/Chicago:20261205T193000");
    expect(file).toContain("SUMMARY:Khruangbin");
    expect(file).toContain("LOCATION:Riviera Theatre\\, Chicago\\, IL");
    expect(file).toContain("URL:https://tickets.example/khruangbin");
    expect(file).toContain("DESCRIPTION:https://tickets.example/khruangbin");
    expect(file).toContain("UID:tm-1@concertscout.app");
    expect(file).toContain("DTSTAMP:20261109T180000Z");
  });

  it("invents no end", () => {
    const file = calendarFile(concert, NOW)!;
    expect(file).not.toMatch(/DTEND|DURATION/);
  });

  it("defines the venue's zone for clients that ignore an unknown TZID", () => {
    const file = lines(calendarFile(concert, NOW)!);
    expect(file.indexOf("BEGIN:VTIMEZONE")).toBeLessThan(file.indexOf("BEGIN:VEVENT"));
    expect(file).toContain("TZID:America/Chicago");
    // December in Chicago is standard time, UTC-6.
    expect(file).toContain("TZOFFSETTO:-0600");
  });

  it("gives a venue in another zone its own offset on that date", () => {
    const summer = lines(calendarFile({ ...concert, date: "2027-07-10", time: "20:00" }, NOW)!);
    expect(summer).toContain("TZOFFSETTO:-0500");
    const tokyo = lines(calendarFile({ ...concert, time_zone: "Asia/Tokyo", time: "19:00" }, NOW)!);
    expect(tokyo).toContain("DTSTART;TZID=Asia/Tokyo:20261205T190000");
    expect(tokyo).toContain("TZOFFSETTO:+0900");
    const kolkata = lines(calendarFile({ ...concert, time_zone: "Asia/Kolkata" }, NOW)!);
    expect(kolkata).toContain("TZOFFSETTO:+0530");
    const london = lines(calendarFile({ ...concert, time_zone: "Europe/London" }, NOW)!);
    expect(london).toContain("TZOFFSETTO:+0000");
  });

  it("takes the offset in force at the Concert's own time, either side of a clock change", () => {
    // US clocks went back on 2026-11-01 at 2:00 AM.
    const before = lines(calendarFile({ ...concert, date: "2026-11-01", time: "00:30:00" }, NOW)!);
    expect(before).toContain("TZOFFSETTO:-0500");
    const after = lines(calendarFile({ ...concert, date: "2026-11-01", time: "20:00:00" }, NOW)!);
    expect(after).toContain("TZOFFSETTO:-0600");
  });

  it("makes a Concert with no time an all-day event on the venue's date", () => {
    const file = lines(calendarFile({ ...concert, time: undefined }, NOW)!);
    expect(file).toContain("DTSTART;VALUE=DATE:20261205");
    expect(file.join("\n")).not.toMatch(/TZID|VTIMEZONE|DTEND/);
    expect(file.find((line) => line.startsWith("DTSTART"))).not.toMatch(/T\d{6}/);
  });

  it("leaves the clock floating when the source gives a time but no zone", () => {
    const file = lines(calendarFile({ ...concert, time_zone: undefined }, NOW)!);
    expect(file).toContain("DTSTART:20261205T193000");
    expect(file.join("\n")).not.toMatch(/TZID|VTIMEZONE/);
  });

  it("writes only what the source reports", () => {
    const bare: Concert = { id: "jb-1", name: "Late Night", url: "https://jambase.example/1", artists: [], date: "2026-12-05" };
    const file = lines(calendarFile(bare, NOW)!);
    expect(file).toContain("SUMMARY:Late Night");
    expect(file.some((line) => line.startsWith("LOCATION"))).toBe(false);
  });

  it("makes no file for a Concert with no date", () => {
    expect(calendarFile({ ...concert, date: undefined }, NOW)).toBeUndefined();
  });

  it("names the event as the listing does, with the Lineup in the description", () => {
    const file = lines(
      calendarFile(
        { ...concert, name: "Khruangbin: A La Sala Tour", artists: [{ name: "Khruangbin" }, { name: "Mdou Moctar" }] },
        NOW,
      )!,
    );
    expect(file).toContain("SUMMARY:Khruangbin: A La Sala Tour");
    expect(file).toContain("DESCRIPTION:Khruangbin\\, Mdou Moctar\\nhttps://tickets.example/khruangbin");
  });

  it("escapes characters the format reserves", () => {
    const file = lines(
      calendarFile(
        {
          ...concert,
          name: "Earth, Wind & Fire; Live, Back\\slash",
          venue: "Hall\nTwo",
        },
        NOW,
      )!,
    );
    expect(file).toContain(String.raw`SUMMARY:Earth\, Wind & Fire\; Live\, Back\\slash`);
    expect(file).toContain(String.raw`LOCATION:Hall\nTwo\, Chicago\, IL`);
  });

  it("ends every line with CRLF and folds long ones at 75 octets without splitting a character", () => {
    const name = "Sigur Rós ".repeat(20).trim();
    const file = calendarFile({ ...concert, name }, NOW)!;
    expect(file.endsWith("\r\n")).toBe(true);
    expect(file.replace(/\r\n/g, "")).not.toMatch(/[\r\n]/);
    for (const line of file.split("\r\n")) {
      expect(new TextEncoder().encode(line).length).toBeLessThanOrEqual(75);
    }
    expect(lines(file)).toContain(`SUMMARY:${name}`);
  });
});

describe("calendarFileName", () => {
  it("names the file after the listing", () => {
    expect(calendarFileName(concert)).toBe("khruangbin.ics");
    expect(calendarFileName({ ...concert, name: "Sigur Rós / AC/DC" })).toBe("sigur-ros-ac-dc.ics");
  });

  it("falls back when nothing usable is left", () => {
    expect(calendarFileName({ ...concert, name: "東京" })).toBe("concert.ics");
  });
});
