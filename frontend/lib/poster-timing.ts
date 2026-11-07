// Presentation begins only after the source has supplied candidates and a Poster.
export const NAME_GAP_MS = 32;
export const PICK_READ_MS = 550;
export const GLIDE_MS = 750;
export const GLIDE_GAP_MS = 100;
export const LANDING_REST_MS = 80;
export const GROW_MS = 450;
export const TICKET_RISE_MS = 420;
export const MAX_CANDIDATE_NAMES = 38;
// Motion starts fast and settles, so a response reads as immediate. Also `--ease-out` in the CSS.
export const EASE_OUT = [0.22, 0.61, 0.36, 1] as const;
export const EASE_OUT_CSS = `cubic-bezier(${EASE_OUT.join(",")})`;

export function namesDuration(count: number): number {
  return Math.min(count, MAX_CANDIDATE_NAMES) * NAME_GAP_MS;
}

export function flyDuration(count: number): number {
  return count > 0 ? GLIDE_MS + (count - 1) * GLIDE_GAP_MS + LANDING_REST_MS + GROW_MS : 0;
}
