import { describe, expect, it } from "vitest";

import { clipLabel, embedSrc, formatStart, type LiveClip } from "@/lib/live-clips";

const clip: LiveClip = {
  video_id: "dQw4w9WgXcQ",
  title: "Khruangbin: Tiny Desk Concert",
  session: "Tiny Desk Concert",
  start: 252,
};

describe("formatStart", () => {
  it.each([
    [0, "0:00"],
    [9, "0:09"],
    [252, "4:12"],
    [3599, "59:59"],
    [3723, "1:02:03"],
  ])("writes %i seconds as %s", (seconds, text) => {
    expect(formatStart(seconds)).toBe(text);
  });
});

describe("clipLabel", () => {
  it("names the session and where the clip jumps to", () => {
    expect(clipLabel(clip)).toBe("Tiny Desk Concert · jumps to 4:12");
  });

  it("names only the session for a clip that starts at its start", () => {
    expect(clipLabel({ ...clip, start: 0 })).toBe("Tiny Desk Concert");
  });
});

describe("embedSrc", () => {
  it("builds YouTube's privacy-enhanced player at the peak, without autoplay", () => {
    expect(embedSrc(clip)).toBe(
      "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?start=252&rel=0",
    );
  });

  it("starts a clip with no peak at 0", () => {
    expect(embedSrc({ ...clip, start: 0 })).toMatch(/\?start=0&rel=0$/);
  });

  it.each(["", "short", "dQw4w9WgXcQ/../x", "dQw4w9WgXc?", "dQw4w9WgXcQQ"])(
    "refuses %j, which is not a video ID",
    (video_id) => {
      expect(embedSrc({ ...clip, video_id })).toBeNull();
    },
  );
});
