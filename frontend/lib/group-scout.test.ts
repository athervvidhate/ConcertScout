import { beforeEach, describe, expect, it } from "vitest";

import {
  forgetRoomMemberId,
  formatDateWindow,
  memberInitials,
  mergeArtists,
  parseArtistsInput,
  readRoomMemberId,
  rememberRoomMemberId,
  sortGroupPicks,
  type GroupPick,
} from "@/lib/group-scout";

function pick(
  id: string,
  counts: { in: number; maybe: number; pass: number },
  consensus = false,
): GroupPick {
  return {
    concert: {
      id,
      name: `Concert ${id}`,
      url: `https://tickets.example/${id}`,
      artists: [{ name: `Artist ${id}` }],
      date: "2026-12-05",
    },
    everyone_fits: true,
    member_matches: [],
    lineup_match: [],
    member_votes: {},
    vote_counts: counts,
    consensus_in: consensus,
  };
}

describe("parseArtistsInput & mergeArtists", () => {
  it("splits commas, newlines and semicolons, deduplicating case-insensitively", () => {
    expect(parseArtistsInput("Khruangbin, Bonobo\nkhruangbin; Four Tet")).toEqual([
      "Khruangbin",
      "Bonobo",
      "Four Tet",
    ]);
  });

  it("merges new artists while preserving existing preference order", () => {
    expect(mergeArtists(["Khruangbin", "Parcels"], ["parcels", "Bonobo"])).toEqual([
      "Khruangbin",
      "Parcels",
      "Bonobo",
    ]);
  });
});

describe("sortGroupPicks", () => {
  it("keeps server Nash ranking in fit mode", () => {
    const list = [
      pick("nash-1", { in: 0, maybe: 0, pass: 0 }),
      pick("nash-2", { in: 2, maybe: 0, pass: 0 }, true),
    ];
    expect(sortGroupPicks(list, "fit").map((p) => p.concert.id)).toEqual(["nash-1", "nash-2"]);
  });

  it("orders by consensus, then In votes, Maybe votes, fewest Pass, then Nash order", () => {
    const list = [
      pick("a", { in: 1, maybe: 0, pass: 1 }),
      pick("b", { in: 1, maybe: 1, pass: 0 }),
      pick("c", { in: 2, maybe: 0, pass: 0 }, true),
      pick("d", { in: 1, maybe: 1, pass: 0 }),
    ];
    expect(sortGroupPicks(list, "votes").map((p) => p.concert.id)).toEqual(["c", "b", "d", "a"]);
  });
});

describe("memberInitials & formatDateWindow", () => {
  it("formats initials cleanly", () => {
    expect(memberInitials("Maya Lin")).toBe("ML");
    expect(memberInitials("Sam")).toBe("SA");
    expect(memberInitials("  ")).toBe("?");
  });

  it("formats date windows without timezone shift", () => {
    expect(formatDateWindow("2026-12-05", "2026-12-05")).toBe("Dec 5");
    expect(formatDateWindow("2026-12-05", "2026-12-12")).toBe("Dec 5 – Dec 12");
    expect(formatDateWindow("2026-12-05", undefined)).toBe("From Dec 5");
    expect(formatDateWindow(undefined, "2026-12-12")).toBe("Until Dec 12");
    expect(formatDateWindow(undefined, undefined)).toBeNull();
  });
});

describe("room member storage", () => {
  beforeEach(() => {
    const store = new Map<string, string>();
    Object.defineProperty(globalThis, "localStorage", {
      value: {
        getItem: (key: string) => store.get(key) ?? null,
        setItem: (key: string, value: string) => store.set(key, value),
        removeItem: (key: string) => store.delete(key),
      },
      configurable: true,
    });
  });

  it("remembers and forgets a member ID per room", () => {
    expect(readRoomMemberId("room-a")).toBeNull();
    rememberRoomMemberId("room-a", "member-1");
    rememberRoomMemberId("room-b", "member-2");
    expect(readRoomMemberId("room-a")).toBe("member-1");
    expect(readRoomMemberId("room-b")).toBe("member-2");
    forgetRoomMemberId("room-a");
    expect(readRoomMemberId("room-a")).toBeNull();
    expect(readRoomMemberId("room-b")).toBe("member-2");
  });
});
