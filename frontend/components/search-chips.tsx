"use client";
import { motion, useReducedMotion } from "motion/react";
import { CalendarDays, MapPin, Music2, UserRound } from "lucide-react";
import { formatMonthDay } from "@/lib/format";
import type { Interpreted } from "@/lib/search";

export function SearchChips({
  interpreted,
  compact = false,
}: {
  interpreted: Interpreted;
  compact?: boolean;
}) {
  const reduced = useReducedMotion();
  const chips = [
    ...interpreted.artists.map((value) => ({
      kind: "artist",
      label: "Artist",
      value,
      Icon: UserRound,
    })),
    ...(interpreted.region || interpreted.place
      ? [
          {
            kind: "place",
            label: "Place",
            value: compact
              ? (interpreted.region ?? interpreted.place!).split(",")[0]
              : (interpreted.region ?? interpreted.place!),
            Icon: MapPin,
          },
        ]
      : []),
    ...interpreted.genres.map((value) => ({
      kind: "sound",
      label: "Sound",
      value,
      Icon: Music2,
    })),
    ...(interpreted.start
      ? [
          {
            kind: "when",
            label: "When",
            value: [
              formatMonthDay(interpreted.start),
              interpreted.end && formatMonthDay(interpreted.end),
            ]
              .filter(Boolean)
              .join(" – "),
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
                ease: [0.34, 1.56, 0.64, 1],
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
