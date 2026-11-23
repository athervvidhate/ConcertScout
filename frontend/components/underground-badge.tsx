"use client";

import type { Concert } from "@/lib/search";
import { isSoldOut, undergroundSourceLabel } from "@/lib/underground";

type UndergroundBadgeProps = {
  concert: Pick<Concert, "source" | "sold_out">;
  variant?: "card" | "ticket";
};

/**
 * Subtle Moss-palette source and status indicators for underground room and curated promoter
 * Concerts. Renders nothing for standard feeds unless the source explicitly reports sold out.
 */
export function UndergroundBadge({
  concert,
  variant = "card",
}: UndergroundBadgeProps) {
  const sourceLabel = undergroundSourceLabel(concert.source);
  const soldOut = isSoldOut(concert);
  if (!sourceLabel && !soldOut) return null;

  return (
    <span className="underground-badges" data-variant={variant}>
      {sourceLabel && (
        <span className="underground-badge" data-source={concert.source}>
          {sourceLabel}
        </span>
      )}
      {soldOut && (
        <span className="sold-out-badge" data-status="sold-out">
          Sold out
        </span>
      )}
    </span>
  );
}
