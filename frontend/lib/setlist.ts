import { useEffect, useState } from "react";

import { formatDate } from "@/lib/format";
import { API_URL, type Concert } from "@/lib/search";

export type SetlistShow = {
  date: string;
  venue?: string;
  city?: string;
};

export type SetlistStaple = {
  name: string;
  shows: number;
  encore_shows: number;
};

export type SetlistSummary = {
  artist: string;
  mbid?: string;
  show_count: number;
  average_songs?: number;
  encore_shows: number;
  last_show?: SetlistShow;
  staples: SetlistStaple[];
  source_url?: string;
};

const SETLISTFM_URL = /^https:\/\/(?:www\.)?setlist\.fm\/.+$/;

/** Only links directly to Setlist.fm over HTTPS are accepted for attribution. */
export function setlistHref(source_url?: string): string | null {
  if (!source_url) return null;
  const trimmed = source_url.trim();
  return SETLISTFM_URL.test(trimmed) ? trimmed : null;
}

export function hasSetlistData(summary: SetlistSummary | null): summary is SetlistSummary {
  return summary !== null && summary.show_count > 0 && summary.staples.length > 0;
}

/** MusicBrainz ID reported for this Artist on the Concert, when present. */
export function artistMbid(concert: Concert, name: string): string | undefined {
  return concert.artists.find((artist) => artist.name === name)?.mbid;
}

export function formatSetlistOverview(summary: SetlistSummary): string {
  const parts: string[] = [];
  if (summary.average_songs !== undefined) {
    const unit = summary.average_songs === 1 ? "song" : "songs";
    parts.push(
      summary.show_count > 1
        ? `${summary.average_songs} ${unit} avg`
        : `${summary.average_songs} ${unit}`,
    );
  }
  parts.push(summary.show_count === 1 ? "1 recent show" : `last ${summary.show_count} shows`);
  if (summary.encore_shows > 0) {
    parts.push(
      summary.show_count === 1
        ? "with encore"
        : `encore in ${summary.encore_shows} of ${summary.show_count}`,
    );
  }
  return parts.join(" · ");
}

export function formatLastShow(show: SetlistShow): string {
  return [formatDate(show.date), show.venue, show.city].filter(Boolean).join(" · ");
}

export function formatStapleCount(staple: SetlistStaple, showCount: number): string {
  const base = `${staple.shows} of ${showCount}`;
  return staple.encore_shows > 0 ? `${base} · encore` : base;
}

type Loaded = { key: string; summary: SetlistSummary };

function empty(artist: string): SetlistSummary {
  return { artist, show_count: 0, encore_shows: 0, staples: [] };
}

/** Loads only once a Ticket Setlist pane or Artist panel opens; never called during Search. */
export function useArtistSetlist(
  name: string,
  mbid: string | undefined,
  open: boolean,
): SetlistSummary | null {
  const key = `${name}\0${mbid ?? ""}`;
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    const query = new URLSearchParams({ name });
    if (mbid) query.set("mbid", mbid);
    fetch(`${API_URL}/artist/setlist?${query}`, { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : empty(name)))
      .then((summary: SetlistSummary) => setLoaded({ key, summary }))
      .catch(() => {
        if (!controller.signal.aborted) setLoaded({ key, summary: empty(name) });
      });
    return () => controller.abort();
  }, [key, name, mbid, open]);

  return loaded?.key === key ? loaded.summary : null;
}
