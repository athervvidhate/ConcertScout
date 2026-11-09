"use client";

import { CalendarPlus } from "lucide-react";

import { downloadCalendar } from "@/lib/calendar";
import type { Concert } from "@/lib/search";

/** Downloads a Concert as a calendar file. A Concert with no date has nothing to add. */
export function AddToCalendar({ concert, name }: { concert: Concert; name: string }) {
  if (!concert.date) return null;
  return (
    <button
      type="button"
      className="calendar-action"
      aria-label={`Add to calendar for ${name}`}
      onClick={() => downloadCalendar(concert)}
    >
      <CalendarPlus aria-hidden size={19} />
      Add to calendar
    </button>
  );
}
