import type { Decision } from "@/lib/saved";

const SWIPE_DISTANCE = 110;
const SWIPE_SPEED = 500;

/** Right saves and left skips. A short, slow drag decides nothing, and the Ticket springs back. */
export function swipeDecision(distance: number, speed: number): Decision | null {
  if (distance > SWIPE_DISTANCE || speed > SWIPE_SPEED) return "saved";
  if (distance < -SWIPE_DISTANCE || speed < -SWIPE_SPEED) return "skipped";
  return null;
}
