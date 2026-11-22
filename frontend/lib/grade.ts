import type { Grade } from "@/lib/search";

const GRADE_LABELS: Record<Grade, string> = {
  seed: "You named them",
  strong: "Close match",
  fair: "Worth a listen",
};

/** The short label for a Recommendation's effective grade, or null when ungraded. */
export function gradeLabel(grade?: Grade | null): string | null {
  if (!grade) return null;
  return GRADE_LABELS[grade] ?? null;
}
