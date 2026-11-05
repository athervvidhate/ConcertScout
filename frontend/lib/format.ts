import type { Interpreted, Price } from "@/lib/search";

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

export function formatDate(date: string): string {
  return dateFormat.format(new Date(`${date}T00:00:00Z`));
}

export function formatTime(time: string): string {
  return timeFormat.format(new Date(`1970-01-01T${time}Z`));
}

export function formatPrice({ min, max, currency }: Price): string {
  const format = new Intl.NumberFormat("en-US", { style: "currency", currency });
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
  return [interpreted.place, formatDates(interpreted), ...interpreted.artists]
    .filter(Boolean)
    .join(" · ");
}
