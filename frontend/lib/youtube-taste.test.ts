import { afterEach, describe, expect, it, vi } from "vitest";

import { SearchRefused } from "@/lib/search";
import { fetchYouTubePlaylistTaste, SOURCE_NAMES } from "@/lib/taste";

describe("fetchYouTubePlaylistTaste", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("posts the playlist URL to /taste/youtube-playlist and returns extracted Artists", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ artists: ["Khruangbin", "Tame Impala"] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const url = "https://music.youtube.com/playlist?list=PLcontractPublic123";
    const artists = await fetchYouTubePlaylistTaste(url);

    expect(artists).toEqual(["Khruangbin", "Tame Impala"]);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/taste\/youtube-playlist$/),
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      }),
    );
    expect(SOURCE_NAMES.youtube).toBe("your YouTube playlist");
  });

  it("throws SearchRefused with the API error message on refusal", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          code: "playlist_private",
          message: "That playlist is private.",
        }),
        { status: 403, headers: { "Content-Type": "application/json" } },
      ),
    );

    await expect(
      fetchYouTubePlaylistTaste("https://www.youtube.com/playlist?list=PLprivate123456"),
    ).rejects.toThrow(SearchRefused);
  });
});
