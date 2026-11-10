"use client";
import { motion, useReducedMotion } from "motion/react";
import { CalendarDays, MapPin, Music2, UserRound } from "lucide-react";
import { formatMonthDay } from "@/lib/format";
import type { Reading } from "@/lib/search";
import { BACK_OUT_CURVE } from "@/lib/choreography";

// An open-ended range says which end is open, so one date never reads as a single day.
function whenOf(start?: string, end?: string): string {
  if (start && end) {
    return start === end
      ? formatMonthDay(start)
      : `${formatMonthDay(start)} – ${formatMonthDay(end)}`;
  }
  return start
    ? `From ${formatMonthDay(start)}`
    : `Until ${formatMonthDay(end!)}`;
}

export function SearchChips({
  reading,
  compact = false,
}: {
  reading: Reading;
  compact?: boolean;
}) {
  const reduced = useReducedMotion();
  const chips = [
    ...reading.artists.map((value) => ({
      kind: "artist",
      label: "Artist",
      value,
      Icon: UserRound,
    })),
    ...(reading.region || reading.place
      ? [
          {
            kind: "place",
            label: "Place",
            value: compact
              ? (reading.region ?? reading.place!).split(",")[0]
              : (reading.region ?? reading.place!),
            Icon: MapPin,
          },
        ]
      : []),
    ...reading.genres.map((value) => ({
      kind: "sound",
      label: "Sound",
      value,
      Icon: Music2,
    })),
    ...(reading.start || reading.end
      ? [
          {
            kind: "when",
            label: "When",
            value: whenOf(reading.start, reading.end),
            Icon: CalendarDays,
          },
        ]
      : []),
  ];
  return (
    <>
      {chips.map(({ kind, label, value, Icon }) => (
        <motion.span
          className="chip"
          data-kind={kind}
          key={`${kind}-${value}`}
          variants={{
            hidden: { opacity: 0, y: 12, scale: 0.85 },
            shown: {
              opacity: 1,
              y: 0,
              scale: 1,
              transition: {
                duration: reduced ? 0 : 0.7,
                ease: BACK_OUT_CURVE,
              },
            },
          }}
        >
          <span className="chip-icon">
            <Icon aria-hidden size={13} />
          </span>
          <span className="chip-kind">{label}</span>
          {value}
        </motion.span>
      ))}
    </>
  );
}
