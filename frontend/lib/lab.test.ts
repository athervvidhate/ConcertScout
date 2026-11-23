import { describe, expect, it } from "vitest";

import {
  formatCostCents,
  formatMs,
  formatPercent,
  jevLevelLabel,
  orderedStepTimings,
  signalLabel,
  stepLabel,
} from "@/lib/lab";

describe("lab formatters", () => {
  it("formats latency in milliseconds and seconds", () => {
    expect(formatMs(null)).toBe("-");
    expect(formatMs(undefined)).toBe("-");
    expect(formatMs(0)).toBe("0 ms");
    expect(formatMs(0.4)).toBe("< 1 ms");
    expect(formatMs(142.6)).toBe("143 ms");
    expect(formatMs(1000)).toBe("1.00 s");
    expect(formatMs(2480)).toBe("2.48 s");
  });

  it("formats Search cost in USD cents and dollars", () => {
    expect(formatCostCents(null)).toBe("-");
    expect(formatCostCents(0)).toBe("0.00¢");
    expect(formatCostCents(0.00001)).toBe("< 0.01¢");
    expect(formatCostCents(0.0014)).toBe("0.14¢");
    expect(formatCostCents(0.025)).toBe("2.50¢");
    expect(formatCostCents(1.25)).toBe("$1.25");
  });

  it("formats cache hit rate percentage", () => {
    expect(formatPercent(null)).toBe("-");
    expect(formatPercent(0)).toBe("0%");
    expect(formatPercent(0.6667)).toBe("67%");
    expect(formatPercent(1)).toBe("100%");
  });

  it("maps match signals and Jev levels to readable labels", () => {
    expect(signalLabel("seed")).toBe("Seed");
    expect(signalLabel("one_hop")).toBe("1-hop");
    expect(signalLabel("two_hops")).toBe("2-hop");
    expect(signalLabel("co_billed")).toBe("Co-billed");
    expect(signalLabel("semantic")).toBe("Semantic");
    expect(signalLabel("tags")).toBe("Tags");
    expect(signalLabel("genre")).toBe("Genre");
    expect(signalLabel(null)).toBe("Notable");

    expect(jevLevelLabel(3)).toBe("3 · Strong fit");
    expect(jevLevelLabel(2)).toBe("2 · Fair fit");
    expect(jevLevelLabel(1)).toBe("1 · Stretch");
    expect(jevLevelLabel(0)).toBe("0 · Unrelated");
    expect(jevLevelLabel(null)).toBe("Ungraded");
  });

  it("orders pipeline step timings deterministically", () => {
    const ordered = orderedStepTimings({
      rank: 420,
      interpret: 120,
      pool: 310,
      semantic: 24,
    });
    expect(ordered.map((item) => item.step)).toEqual([
      "interpret",
      "pool",
      "semantic",
      "rank",
    ]);
    expect(ordered.map((item) => item.label)).toEqual([
      stepLabel("interpret"),
      stepLabel("pool"),
      stepLabel("semantic"),
      stepLabel("rank"),
    ]);
  });
});
