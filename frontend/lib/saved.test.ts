import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  removeSaved,
  saveConcert,
  skipConcert,
  upcoming,
  useDecisions,
  useSavedConcerts,
} from "@/lib/saved";
import type { Recommendation } from "@/lib/search";

function recommendation(id: string, date?: string): Recommendation {
  return { concert: { id, name: id, url: "https://x", artists: [], date }, reason: "fit" };
}

beforeEach(() => localStorage.clear());

describe("Saved Concerts", () => {
  it("keeps a saved Concert in storage, so it survives a reload", () => {
    saveConcert(recommendation("a"));

    const { result } = renderHook(() => useSavedConcerts());

    expect(result.current.map((r) => r.concert.id)).toEqual(["a"]);
  });

  it("does not store a Concert twice", () => {
    saveConcert(recommendation("a"));
    saveConcert(recommendation("a"));

    expect(renderHook(() => useSavedConcerts()).result.current).toHaveLength(1);
  });

  it("removes a saved Concert when it is skipped, and the reverse", () => {
    const { result } = renderHook(() => useDecisions());

    act(() => saveConcert(recommendation("a")));
    expect(result.current).toEqual({ a: "saved" });

    act(() => skipConcert("a"));
    expect(result.current).toEqual({ a: "skipped" });
    expect(renderHook(() => useSavedConcerts()).result.current).toEqual([]);

    act(() => saveConcert(recommendation("a")));
    expect(result.current).toEqual({ a: "saved" });
  });

  it("removes a Concert from the list", () => {
    saveConcert(recommendation("a"));
    const { result } = renderHook(() => useSavedConcerts());

    act(() => removeSaved("a"));

    expect(result.current).toEqual([]);
  });

  it("treats unreadable storage as empty", () => {
    localStorage.setItem("concert-scout-saved", "not json");

    expect(renderHook(() => useSavedConcerts()).result.current).toEqual([]);
  });

  it("reports a refused save to the caller", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementationOnce(() => {
      throw new Error("denied");
    });

    expect(() => saveConcert(recommendation("a"))).toThrow("denied");
    vi.restoreAllMocks();
  });
});

describe("upcoming", () => {
  it("hides past Concerts and keeps today and undated ones", () => {
    const saved = [
      recommendation("past", "2026-11-04"),
      recommendation("today", "2026-11-05"),
      recommendation("undated"),
    ];

    const kept = upcoming(saved, "2026-11-05").map((r) => r.concert.id);

    expect(kept).toEqual(["today", "undated"]);
  });
});
