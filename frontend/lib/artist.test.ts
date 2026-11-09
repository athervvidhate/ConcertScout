import { describe, expect, it } from "vitest";

import { type ArtistProfile, previewSrc, spotifyHref } from "@/lib/artist";

const profile: ArtistProfile = { name: "Son Volt", tags: [], top_tracks: [], similar: [] };

describe("spotifyHref", () => {
  it("prefers the Artist's exact page", () => {
    const url = "https://open.spotify.com/artist/son-volt";
    expect(spotifyHref({ ...profile, spotify_url: url })).toBe(url);
  });

  it("falls back to a Spotify search for the name", () => {
    expect(spotifyHref(profile)).toBe("https://open.spotify.com/search/Son%20Volt");
  });
});

describe("previewSrc", () => {
  const id = "4Z8W4fKeB5YxbusRsdQVPb";

  it("builds Spotify's player from the Artist's exact page", () => {
    expect(previewSrc({ ...profile, spotify_url: `https://open.spotify.com/artist/${id}` })).toBe(
      `https://open.spotify.com/embed/artist/${id}`,
    );
  });

  it.each([
    ["no page", undefined],
    ["a search link", "https://open.spotify.com/search/Son%20Volt"],
    ["another host", `https://evil.example/artist/${id}`],
    ["a lookalike host", `https://open.spotify.com.evil.example/artist/${id}`],
    ["plain http", `http://open.spotify.com/artist/${id}`],
    ["a short ID", "https://open.spotify.com/artist/son-volt"],
    ["a path in the ID", `https://open.spotify.com/artist/${id}/../../x`],
    ["a query", `https://open.spotify.com/artist/${id}?x=1`],
    ["a script", 'https://open.spotify.com/artist/"><script>alert(1)</script>'],
  ])("builds nothing from %s", (_, spotify_url) => {
    expect(previewSrc({ ...profile, spotify_url })).toBeNull();
  });
});
