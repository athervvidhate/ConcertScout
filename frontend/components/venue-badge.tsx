"use client";

import { formatVenueCharacter, useVenueCharacter } from "@/lib/venues";

type VenueBadgeProps = {
  name: string;
  city?: string;
  lat?: number;
  lon?: number;
};

/** Verified room character beside a Ticket's venue name. Omitted when unverified. */
export function VenueBadge({ name, city, lat, lon }: VenueBadgeProps) {
  const venue = useVenueCharacter(name, city, lat, lon);
  if (!venue) return null;
  const label = formatVenueCharacter(venue);
  if (!label) return null;

  return (
    <span className="venue-badge" title={venue.venue_type ?? undefined}>
      <span aria-hidden="true"> · </span>
      {label}
    </span>
  );
}
