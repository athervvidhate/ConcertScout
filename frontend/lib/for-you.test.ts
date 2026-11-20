import { describe, expect, it } from "vitest";

import {
  noteFor,
  reconcile,
  shelfTitle,
  type TasteProfile,
} from "@/lib/for-you";
import type { ImportedTaste } from "@/lib/taste";

const local = (importedAt: string, ...artists: string[]): ImportedTaste => ({
  source: "seed",
  artists,
  importedAt,
});
const remote = (updated_at: string, ...artists: string[]): TasteProfile => ({
  source: "seed",
  artists,
  updated_at,
});

describe("which Taste wins at sign-in", () => {
  it("brings an Account's Taste to a device that has none", () => {
    expect(reconcile(null, remote("2026-11-20T10:00:00Z", "Khruangbin"))).toBe(
      "pull",
    );
  });

  it("sends a device's Taste to an Account that has none", () => {
    expect(reconcile(local("2026-11-20T10:00:00Z", "Khruangbin"), null)).toBe(
      "push",
    );
  });

  it("does nothing when both are empty or the same", () => {
    expect(reconcile(null, null)).toBe("none");
    expect(
      reconcile(
        local("2026-11-01T00:00:00Z", "Khruangbin"),
        remote("2026-11-20T00:00:00Z", "Khruangbin"),
      ),
    ).toBe("none");
  });

  it("keeps whichever side was saved last", () => {
    const older = local("2026-11-01T00:00:00Z", "Old");
    expect(reconcile(older, remote("2026-11-20T00:00:00Z", "New"))).toBe(
      "pull",
    );
    const newer = local("2026-11-21T00:00:00Z", "New");
    expect(reconcile(newer, remote("2026-11-20T00:00:00Z", "Old"))).toBe(
      "push",
    );
  });

  it("treats a device Taste with no date as older", () => {
    const undated: ImportedTaste = { source: "list", artists: ["Old"] };
    expect(reconcile(undated, remote("2026-11-20T00:00:00Z", "New"))).toBe(
      "pull",
    );
  });
});

describe("the shelf's words", () => {
  it("names the Taste Artist behind each reason, never a model's guess", () => {
    expect(noteFor({ signal: "seed", via: "Khruangbin" })).toBe(
      "An Artist in your Taste",
    );
    expect(noteFor({ signal: "one_hop", via: "Khruangbin" })).toBe(
      "Similar to Khruangbin",
    );
    expect(noteFor({ signal: "co_billed", via: "Khruangbin" })).toBe(
      "Often on the same bill as Khruangbin",
    );
  });

  it("says where it looked", () => {
    expect(shelfTitle("Near you")).toBe("For You near you");
    expect(shelfTitle("San Francisco, California")).toBe(
      "For You near San Francisco",
    );
  });
});
