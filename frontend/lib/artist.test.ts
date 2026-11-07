import { describe, expect, it } from "vitest";

import { type ArtistProfile, spotifyHref } from "@/lib/artist";

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
