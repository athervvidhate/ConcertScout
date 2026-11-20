import { describe, expect, it } from "vitest";

import type { Concert } from "@/lib/search";
import {
  type SetlistSummary,
  artistMbid,
  formatLastShow,
  formatSetlistOverview,
  formatStapleCount,
  hasSetlistData,
  setlistHref,
} from "@/lib/setlist";

const summary: SetlistSummary = {
  artist: "Khruangbin",
  mbid: "83d91898-7763-47d7-b03b-b92132375c47",
  show_count: 5,
  average_songs: 18,
  encore_shows: 4,
  last_show: {
    date: "2026-10-24",
    venue: "Greek Theatre",
    city: "Berkeley, CA",
  },
  staples: [
    { name: "May Ninth", shows: 5, encore_shows: 0 },
    { name: "People Everywhere (Still Alive)", shows: 5, encore_shows: 4 },
  ],
  source_url: "https://www.setlist.fm/setlists/khruangbin-23da00bb.html",
};

describe("setlistHref", () => {
  it("accepts Setlist.fm HTTPS links", () => {
    expect(setlistHref(summary.source_url)).toBe(summary.source_url);
    expect(setlistHref("https://setlist.fm/setlist/test.html")).toBe(
      "https://setlist.fm/setlist/test.html",
    );
  });

  it.each([
    ["missing", undefined],
    ["plain http", "http://www.setlist.fm/setlists/khruangbin-23da00bb.html"],
    ["other host", "https://evil.example/setlists/khruangbin"],
    ["lookalike host", "https://www.setlist.fm.evil.example/setlists/khruangbin"],
    ["javascript", "javascript:alert(1)"],
  ])("rejects %s URLs", (_, url) => {
    expect(setlistHref(url)).toBeNull();
  });
});

describe("hasSetlistData", () => {
  it("requires both shows and staples", () => {
    expect(hasSetlistData(summary)).toBe(true);
    expect(hasSetlistData(null)).toBe(false);
    expect(hasSetlistData({ ...summary, show_count: 0 })).toBe(false);
    expect(hasSetlistData({ ...summary, staples: [] })).toBe(false);
  });
});

describe("formatting", () => {
  it("formats overview with and without encores", () => {
    expect(formatSetlistOverview(summary)).toBe("18 songs avg · last 5 shows · encore in 4 of 5");
    expect(formatSetlistOverview({ ...summary, show_count: 1, encore_shows: 0 })).toBe(
      "18 songs · 1 recent show",
    );
    expect(formatSetlistOverview({ ...summary, show_count: 1, encore_shows: 1 })).toBe(
      "18 songs · 1 recent show · with encore",
    );
  });

  it("omits missing last-show fields cleanly", () => {
    expect(formatLastShow(summary.last_show!)).toBe("Sat, Oct 24, 2026 · Greek Theatre · Berkeley, CA");
    expect(formatLastShow({ date: "2026-10-24" })).toBe("Sat, Oct 24, 2026");
  });

  it("formats staple appearance counts and encore markers", () => {
    expect(formatStapleCount(summary.staples[0], 5)).toBe("5 of 5");
    expect(formatStapleCount(summary.staples[1], 5)).toBe("5 of 5 · encore");
  });
});

describe("artistMbid", () => {
  const concert: Concert = {
    id: "c1",
    name: "Khruangbin",
    url: "https://tickets.example/c1",
    artists: [{ name: "Khruangbin", mbid: summary.mbid }, { name: "Opener" }],
  };

  it("finds the matching Artist MBID when reported", () => {
    expect(artistMbid(concert, "Khruangbin")).toBe(summary.mbid);
    expect(artistMbid(concert, "Opener")).toBeUndefined();
    expect(artistMbid(concert, "Unknown")).toBeUndefined();
  });
});
