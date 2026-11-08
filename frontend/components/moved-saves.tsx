"use client";

import { countOf } from "@/lib/format";
import { useSavedConcerts } from "@/lib/saved";

/** Says what signing in moved from this device into the account. */
export function MovedSaves() {
  const { moved } = useSavedConcerts();
  if (!moved) return null;
  const parts = [];
  if (moved.added) parts.push(`Moved ${countOf(moved.added, "Saved Concert")} from this device into your account.`);
  if (moved.left) {
    parts.push(
      `${countOf(moved.left, "Saved Concert")} could not be confirmed with Ticketmaster and stayed on this device. The next sign-in tries again.`,
    );
  }
  return (
    <p className="account-note" role="status">
      {parts.join(" ")}
    </p>
  );
}
