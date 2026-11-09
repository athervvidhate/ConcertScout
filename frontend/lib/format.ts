import type { Concert, Interpreted, Price } from "@/lib/search";

// Concert dates and times are local to the venue, so format them in UTC to keep them unshifted.
const dateFormat = new Intl.DateTimeFormat("en-US", {
  weekday: "short",
  month: "short",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC",
});

const timeFormat = new Intl.DateTimeFormat("en-US", {
  hour: "numeric",
  minute: "2-digit",
  timeZone: "UTC",
});

const monthDayFormat = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

const dayFormat = new Intl.DateTimeFormat("en-US", { weekday: "short", timeZone: "UTC" });

export function formatDate(date: string): string {
  return dateFormat.format(new Date(`${date}T00:00:00Z`));
}

export function viewerZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

/** The calendar day in a zone, in the same form as a Concert's date. */
export function dateIn(zone: string, now: Date): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: zone }).format(now);
}

export function formatMonthDay(date: string): string {
  return monthDayFormat.format(new Date(`${date}T00:00:00Z`));
}

export function formatDayShort(date: string): string {
  return dayFormat.format(new Date(`${date}T00:00:00Z`));
}

export function formatTime(time: string): string {
  return timeFormat.format(new Date(`1970-01-01T${time}Z`));
}

function zoneName(zone: string, style: "short" | "longOffset", at: Date): string | undefined {
  const parts = new Intl.DateTimeFormat("en-US", { timeZone: zone, timeZoneName: style }).formatToParts(at);
  return parts.find(({ type }) => type === "timeZoneName")?.value;
}

/** The venue's own clock. A visitor elsewhere also sees which zone that clock is in. */
export function formatConcertTime({ date, time, time_zone }: Concert, viewer = viewerZone()): string | undefined {
  if (!time) return undefined;
  const clock = formatTime(time);
  if (!date || !time_zone) return clock;
  // Treating the venue's clock as UTC lands within a day of the real moment, near enough to read a zone.
  const at = new Date(`${date}T${time}Z`);
  if (zoneName(viewer, "longOffset", at) === zoneName(time_zone, "longOffset", at)) return clock;
  return `${clock} ${zoneName(time_zone, "short", at)}`;
}

// Unlike a Concert's times, a sale opens at one moment, so it reads in the visitor's own zone.
const saleFormat = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

/** An Artist's dates gathered by venue, so a run of shows reads as one place. */
export function byVenue(concerts: Concert[]): Concert[][] {
  const venues = new Map<string, Concert[]>();
  for (const concert of concerts) {
    const key = [concert.venue, concert.city, concert.region].join("|");
    venues.set(key, [...(venues.get(key) ?? []), concert]);
  }
  return [...venues.values()];
}

/** The next presale, for a Concert not yet on general sale. */
export function presaleLine({ general_sale, presales = [] }: Concert, now = new Date()): string | null {
  if (general_sale && new Date(general_sale) <= now) return null;
  const [next] = presales
    .filter(({ end }) => new Date(end) > now)
    .sort((a, b) => a.start.localeCompare(b.start));
  if (!next) return null;
  const start = new Date(next.start);
  return start <= now ? `${next.name} on now` : `${next.name} starts ${saleFormat.format(start)}`;
}

export function formatPrice({ min, max, currency }: Price, compact = false): string {
  const format = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    // Compact drops ".00", but a real price keeps its cents, so $38.30 never reads $38.3.
    ...(compact && Number.isInteger(min) && Number.isInteger(max) ? { minimumFractionDigits: 0 } : {}),
  });
  return min === max ? format.format(min) : `${format.format(min)} to ${format.format(max)}`;
}

function formatDates({ start, end }: Interpreted): string | null {
  if (start && end) {
    return start === end ? formatDate(start) : `${formatDate(start)} to ${formatDate(end)}`;
  }
  if (start) return `from ${formatDate(start)}`;
  if (end) return `until ${formatDate(end)}`;
  return null;
}

export function formatInterpreted(interpreted: Interpreted): string {
  return [interpreted.region ?? interpreted.place, formatDates(interpreted), ...interpreted.artists]
    .filter(Boolean)
    .join(" · ");
}

function headingDates(start?: string, end?: string): string | null {
  if (start && end) {
    if (start === end) return formatMonthDay(start);
    if (start.slice(0, 4) !== end.slice(0, 4)) {
      return `${formatMonthDay(start)}, ${start.slice(0, 4)} to ${formatMonthDay(end)}, ${end.slice(0, 4)}`;
    }
    const sameMonth = start.slice(0, 7) === end.slice(0, 7);
    return `${formatMonthDay(start)} to ${sameMonth ? Number(end.slice(8)) : formatMonthDay(end)}`;
  }
  if (start) return `from ${formatMonthDay(start)}`;
  if (end) return `until ${formatMonthDay(end)}`;
  return null;
}

export function formatPosterHeading({ place, region, start, end, artists }: Interpreted): string {
  return [region ?? place, headingDates(start, end)].filter(Boolean).join(", ") || artists.join(", ");
}

export function countOf(count: number, noun: string): string {
  return count === 1 ? `1 ${noun}` : `${count} ${noun}s`;
}
