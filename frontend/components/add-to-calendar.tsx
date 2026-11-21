"use client";

import { CalendarPlus } from "lucide-react";

import { downloadCalendar } from "@/lib/calendar";
import type { Concert } from "@/lib/search";

/** Downloads a Concert as a calendar file. A Concert with no date has nothing to add. */
export function AddToCalendar({
  concert,
  name,
  iconOnly = false,
}: {
  concert: Concert;
  name: string;
  iconOnly?: boolean;
}) {
  if (!concert.date) return null;
  return (
    <button
      type="button"
      className={iconOnly ? "calendar-action icon" : "calendar-action"}
      aria-label={`Add to calendar for ${name}`}
      title="Add to calendar"
      onClick={() => downloadCalendar(concert)}
    >
      <CalendarPlus aria-hidden size={19} />
      {!iconOnly && "Add to calendar"}
    </button>
  );
}
