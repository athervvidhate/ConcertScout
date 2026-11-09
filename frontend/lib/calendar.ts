import { zoneName } from "@/lib/format";
import type { Concert } from "@/lib/search";

/**
 * A Concert as an iCalendar (RFC 5545) file, built from the source record alone. The `ics`
 * package writes a local time without its zone, so a timed event would lose the venue's clock.
 */

const CRLF = "\r\n";
const encoder = new TextEncoder();

function text(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r\n|\r|\n/g, "\\n");
}

// A content line stops at 75 octets and a fold never splits a character.
function fold(line: string): string {
  const parts: string[] = [];
  let current = "";
  let size = 0;
  for (const character of line) {
    const bytes = encoder.encode(character).length;
    if (size + bytes > (parts.length === 0 ? 75 : 74)) {
      parts.push(current);
      current = "";
      size = 0;
    }
    current += character;
    size += bytes;
  }
  parts.push(current);
  return parts.join(`${CRLF} `);
}

function stamp(at: Date): string {
  return at.toISOString().replace(/[-:]|\.\d{3}/g, "");
}

// The source's "19:30" or "19:30:00" as hours, minutes and seconds.
function clockParts(time: string): [string, string, string] {
  const [hours = "00", minutes = "00", seconds = "00"] = time.split(":");
  return [hours, minutes, seconds.slice(0, 2)];
}

function clock(time: string): string {
  return clockParts(time).join("");
}

function offsetAt(zone: string, at: Date): number {
  const match = /^GMT(?:([+-])(\d{1,2}):(\d{2}))?$/.exec(zoneName(zone, "longOffset", at) ?? "");
  if (!match?.[1]) return 0;
  return (match[1] === "-" ? -1 : 1) * (Number(match[2]) * 60 + Number(match[3]));
}

/** The venue's offset from UTC, in minutes, at a wall-clock time there. */
function venueOffset(zone: string, date: string, time: string): number {
  const wall = new Date(`${date}T${clockParts(time).join(":")}Z`);
  return offsetAt(zone, new Date(wall.getTime() - offsetAt(zone, wall) * 60_000));
}

function formatOffset(minutes: number): string {
  const absolute = Math.abs(minutes);
  const sign = minutes < 0 ? "-" : "+";
  return `${sign}${String(Math.floor(absolute / 60)).padStart(2, "0")}${String(absolute % 60).padStart(2, "0")}`;
}

// Outlook ignores a TZID that nothing defines. This defines the zone as the offset the venue
// keeps on that day, which is all one event needs.
function timezone(zone: string, offset: string): string[] {
  return [
    "BEGIN:VTIMEZONE",
    `TZID:${zone}`,
    "BEGIN:STANDARD",
    "DTSTART:19700101T000000",
    `TZOFFSETFROM:${offset}`,
    `TZOFFSETTO:${offset}`,
    "END:STANDARD",
    "END:VTIMEZONE",
  ];
}

/** The Lineup, when it says something the listing's name does not. */
function lineupOf({ artists, name }: Concert): string | undefined {
  const lineup = artists.map((artist) => artist.name).join(", ");
  return lineup && lineup.toLowerCase() !== name.toLowerCase() ? lineup : undefined;
}

/**
 * The calendar file for a Concert, or nothing without a date, which cannot be invented. With no
 * time the event is all-day on the venue's date. The source reports no end, so none is written.
 */
export function calendarFile(concert: Concert, now = new Date()): string | undefined {
  const { date, time, time_zone, id, url, venue, city, region } = concert;
  if (!date) return undefined;
  const day = date.replaceAll("-", "");
  const location = [venue, city, region].filter(Boolean).join(", ");

  let start: string;
  let zone: string[] = [];
  if (!time) start = `DTSTART;VALUE=DATE:${day}`;
  else if (!time_zone) start = `DTSTART:${day}T${clock(time)}`;
  else {
    start = `DTSTART;TZID=${time_zone}:${day}T${clock(time)}`;
    zone = timezone(time_zone, formatOffset(venueOffset(time_zone, date, time)));
  }

  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Concert Scout//Add to calendar//EN",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    ...zone,
    "BEGIN:VEVENT",
    `UID:${text(id)}@concertscout.app`,
    `DTSTAMP:${stamp(now)}`,
    start,
    `SUMMARY:${text(concert.name)}`,
    ...(location ? [`LOCATION:${text(location)}`] : []),
    `DESCRIPTION:${text([lineupOf(concert), url].filter(Boolean).join("\n"))}`,
    `URL:${url}`,
    "END:VEVENT",
    "END:VCALENDAR",
  ];
  return lines.map(fold).join(CRLF) + CRLF;
}

/** A file name from the listing's name, with nothing a file system refuses. */
export function calendarFileName(concert: Concert): string {
  const slug = concert.name
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+/, "")
    .slice(0, 60)
    .replace(/-+$/, "");
  return `${slug || "concert"}.ics`;
}

/** Saves the file through the browser with no request. False for a Concert with no date. */
export function downloadCalendar(concert: Concert): boolean {
  const file = calendarFile(concert);
  if (!file) return false;
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([file], { type: "text/calendar;charset=utf-8" }));
  link.download = calendarFileName(concert);
  document.body.append(link);
  link.click();
  link.remove();
  // Safari can read the blob well after the click, so it is released later, as FileSaver.js does.
  setTimeout(() => URL.revokeObjectURL(link.href), 40_000);
  return true;
}
