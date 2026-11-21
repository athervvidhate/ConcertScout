import { describe, expect, it } from "vitest";

import {
  findSourceForNote,
  formatWeekdays,
  planUndo,
  posterArtistNames,
  type RefinementEntry,
} from "@/lib/refinement";
import type { Reading, Recommendation } from "@/lib/search";

const BASE_READING: Reading = {
  artists: ["Fred again.."],
  descriptors: [],
  tags: ["uk garage"],
  genres: ["Dance/Electronic"],
  place: "San Francisco, California, United States",
};

const RECS: Recommendation[] = [
  {
    concert: {
      id: "c1",
      name: "Sammy Virji Live",
      url: "https://tickets.example/c1",
      artists: [{ name: "Sammy Virji" }],
    },
  },
  {
    concert: {
      id: "c2",
      name: "Jamie xx Live",
      url: "https://tickets.example/c2",
      artists: [{ name: "Jamie xx" }],
    },
  },
];

describe("posterArtistNames", () => {
  it("extracts ordered unique Artist names from Recommendations", () => {
    expect(posterArtistNames([...RECS, RECS[0]])).toEqual([
      "Sammy Virji",
      "Jamie xx",
    ]);
  });
});

describe("findSourceForNote", () => {
  it("prefers the backend source_url when provided", () => {
    const source = findSourceForNote(
      {
        text: "is it all ages?",
        message: "Concert Scout can't tell.",
        artist: "Jamie xx",
        source_url: "https://tickets.example/from-session",
        source_label: "Jamie xx",
      },
      RECS,
    );
    expect(source).toEqual({
      url: "https://tickets.example/from-session",
      label: "Jamie xx",
    });
  });

  it("matches the referenced Poster Artist when backend had no session", () => {
    const source = findSourceForNote(
      {
        text: "is Jamie xx all ages?",
        message: "Concert Scout can't tell.",
        artist: "Jamie xx",
      },
      RECS,
    );
    expect(source).toEqual({
      url: "https://tickets.example/c2",
      label: "Jamie xx",
    });
  });

  it("falls back to the first Poster Concert URL", () => {
    const source = findSourceForNote(
      {
        text: "where do I park?",
        message: "Concert Scout can't tell.",
      },
      RECS,
    );
    expect(source).toEqual({
      url: "https://tickets.example/c1",
      label: "Sammy Virji",
    });
  });
});

describe("planUndo", () => {
  const wkndReading: Reading = { ...BASE_READING, weekends_only: true };
  const cheapReading: Reading = { ...wkndReading, max_price: 40 };
  const trail: RefinementEntry[] = [
    { id: "r1", text: "Only weekends", label: "Weekends only", reading: wkndReading },
    { id: "r2", text: "cheaper", label: "Under $40", reading: cheapReading },
  ];

  it("restores the previous Reading when undoing the latest chip", () => {
    const plan = planUndo(trail, 1, BASE_READING);
    expect(plan.nextTrail).toEqual([trail[0]]);
    expect(plan.restoreReading).toEqual(wkndReading);
    expect(plan.replayText).toBeUndefined();
  });

  it("restores the base Reading when undoing the only chip", () => {
    const plan = planUndo([trail[0]], 0, BASE_READING);
    expect(plan.nextTrail).toEqual([]);
    expect(plan.restoreReading).toEqual(BASE_READING);
    expect(plan.replayText).toBeUndefined();
  });

  it("replays remaining Refinements when undoing an earlier chip", () => {
    const plan = planUndo(trail, 0, BASE_READING);
    expect(plan.nextTrail).toEqual([]);
    expect(plan.restoreReading).toEqual(BASE_READING);
    expect(plan.replayText).toBe("cheaper");
  });
});

describe("formatWeekdays", () => {
  it("formats single days, weekends, and custom weekday lists", () => {
    expect(formatWeekdays([5])).toBe("Saturdays");
    expect(formatWeekdays([4, 5, 6])).toBe("Weekends");
    expect(formatWeekdays([4, 5])).toBe("Fri, Sat");
  });
});
