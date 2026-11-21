import { expect, test } from "vitest";

import { gradeLabel } from "@/lib/grade";
import type { Grade } from "@/lib/search";

test("maps each effective grade level to its display label", () => {
  expect(gradeLabel("seed")).toBe("You named them");
  expect(gradeLabel("strong")).toBe("Close match");
  expect(gradeLabel("fair")).toBe("Worth a listen");
});

test("returns null for missing or ungraded values without inventing a label", () => {
  expect(gradeLabel(undefined)).toBeNull();
  expect(gradeLabel(null)).toBeNull();
  expect(gradeLabel("" as unknown as Grade)).toBeNull();
  expect(gradeLabel("unknown" as unknown as Grade)).toBeNull();
});
