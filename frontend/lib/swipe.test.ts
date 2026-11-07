import { describe, expect, it } from "vitest";

import { swipeDecision } from "@/lib/swipe";

describe("swipeDecision", () => {
  it("saves on a long drag right and skips on a long drag left", () => {
    expect(swipeDecision(140, 0)).toBe("saved");
    expect(swipeDecision(-140, 0)).toBe("skipped");
  });

  it("counts a quick flick as a decision", () => {
    expect(swipeDecision(30, 800)).toBe("saved");
    expect(swipeDecision(-30, -800)).toBe("skipped");
  });

  it("decides nothing on a short, slow drag", () => {
    expect(swipeDecision(40, 100)).toBeNull();
  });
});
