import { describe, expect, it } from "vitest";
import { flyDuration, namesDuration } from "./poster-timing";

describe("Poster presentation timing", () => {
  it("limits the stagger to 38 candidate names", () => {
    expect(namesDuration(60)).toBe(38 * 32);
  });

  it("waits for the last of eight names before the shared grow", () => {
    expect(flyDuration(8)).toBe(1980);
    expect(flyDuration(0)).toBe(0);
  });
});
