import { useEffect, useState } from "react";

import { API_URL } from "@/lib/search";

/** An official live video of an Artist, and the second its peak moment starts at. */
export type LiveClip = {
  video_id: string;
  title: string;
  // The series or channel that filmed it, such as "Tiny Desk Concert".
  session: string;
  start: number;
};

/** "4:12", or "1:02:03" once the clip passes an hour. */
export function formatStart(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = String(seconds % 60).padStart(2, "0");
  return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${rest}` : `${minutes}:${rest}`;
}

/** "Tiny Desk Concert · jumps to 4:12". A clip that starts at its start only names its session. */
export function clipLabel({ session, start }: LiveClip): string {
  return start > 0 ? `${session} · jumps to ${formatStart(start)}` : session;
}

const VIDEO_ID = /^[A-Za-z0-9_-]{11}$/;

/** YouTube's privacy-enhanced player at the peak moment, or null for anything but a video ID. */
export function embedSrc({ video_id, start }: LiveClip): string | null {
  if (!VIDEO_ID.test(video_id)) return null;
  return `https://www.youtube-nocookie.com/embed/${video_id}?start=${Math.max(0, Math.trunc(start))}&rel=0`;
}

export type LiveLookup = { clip: LiveClip | null } | { error: string };

type Loaded = { name: string; lookup: LiveLookup };

/** Looks up only once Watch Live is pressed, so a Poster costs YouTube nothing. Null while it loads. */
export function useLiveClip(name: string, open: boolean): LiveLookup | null {
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    const query = new URLSearchParams({ name });
    const unavailable = { error: "Live clips are not answering. Try again soon." };
    fetch(`${API_URL}/artist/live-clip?${query}`, { signal: controller.signal })
      .then(async (response): Promise<LiveLookup> => {
        if (response.ok) return response.json();
        const failure: { message?: string } = await response.json().catch(() => ({}));
        return { error: failure.message ?? unavailable.error };
      })
      .then((lookup) => setLoaded({ name, lookup }))
      .catch(() => {
        if (!controller.signal.aborted) setLoaded({ name, lookup: unavailable });
      });
    return () => controller.abort();
  }, [name, open]);

  return loaded?.name === name ? loaded.lookup : null;
}
