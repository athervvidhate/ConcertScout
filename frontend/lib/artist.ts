import { useEffect, useState } from "react";

import { API_URL } from "@/lib/search";

export type ArtistProfile = {
  name: string;
  lastfm_url?: string;
  spotify_url?: string;
  listeners?: number;
  bio?: string;
  tags: string[];
  top_tracks: { name: string; url: string }[];
  similar: string[];
};

/** With no exact page from Spotify, its own search is still an honest link. */
export function spotifyHref({ name, spotify_url }: ArtistProfile): string {
  return spotify_url ?? `https://open.spotify.com/search/${encodeURIComponent(name)}`;
}

type Loaded = { name: string; profiles: ArtistProfile[] };

function blank(name: string): ArtistProfile[] {
  return [{ name, tags: [], top_tracks: [], similar: [] }];
}

/** Loads only once a panel is open, so a Poster costs no lookups. */
export function useArtistProfiles(name: string, open: boolean) {
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    const query = new URLSearchParams({ name });
    fetch(`${API_URL}/artist?${query}`, { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : { profiles: blank(name) }))
      .then(({ profiles }: { profiles: ArtistProfile[] }) => setLoaded({ name, profiles }))
      .catch(() => {
        if (!controller.signal.aborted) setLoaded({ name, profiles: blank(name) });
      });
    return () => controller.abort();
  }, [name, open]);

  return loaded?.name === name ? loaded.profiles : null;
}
