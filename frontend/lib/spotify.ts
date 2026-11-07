import { useCallback, useEffect, useRef, useState } from "react";

import { API_URL } from "@/lib/search";

const ROOT = `${API_URL}/auth/spotify`;
const MESSAGES: Record<string, string> = {
  connected: "Spotify connected. Your Artists have their own shelf.",
  not_allowed: "This Spotify account is not on the app's invite list. Use a history file or another Taste import instead.",
  unavailable: "Spotify could not connect. Try again soon.",
  cancelled: "Spotify connection cancelled.",
};

const SHELF_HIDDEN_KEY = "concert-scout-shelf-hidden";

/** Whether the visitor closed the shelf. It stays on this device. */
export function readShelfHidden(): boolean {
  try {
    return localStorage.getItem(SHELF_HIDDEN_KEY) !== null;
  } catch {
    return false;
  }
}

export function keepShelfHidden(hidden: boolean): void {
  try {
    if (hidden) localStorage.setItem(SHELF_HIDDEN_KEY, "1");
    else localStorage.removeItem(SHELF_HIDDEN_KEY);
  } catch {
    // Without storage, the shelf only opens again on the next visit.
  }
}

export type SpotifyConnection = {
  available: boolean;
  connected: boolean;
  message: string | null;
  connectHref: string | null;
  disconnect: () => Promise<void>;
};

// Spotify account data has no route into imported Taste or /search.
export function useSpotifyConnection(): SpotifyConnection {
  const [state, setState] = useState({available: false, connected: false, message: null as string | null, connectHref: null as string | null});
  // Focus can start a status check at any time, so only the newest question may answer.
  const asked = useRef(0);
  const refresh = useCallback(async () => {
    const question = ++asked.current;
    try {
      const response = await fetch(`${ROOT}/status`, {credentials: "include", cache: "no-store"});
      if (!response.ok) return;
      const status: {available: boolean; connected: boolean} = await response.json();
      if (question !== asked.current) return;
      setState(old => ({...old, ...status, connectHref: `${ROOT}/login?return_to=${encodeURIComponent(window.location.origin)}`}));
    } catch {
      // Optional connection status must never stop the ordinary Search or local imports.
    }
  }, []);

  useEffect(() => {
    const result = new URLSearchParams(window.location.search).get("spotify");
    if (result) {
      const message = MESSAGES[result] ?? null;
      const url = new URL(window.location.href);
      url.searchParams.delete("spotify");
      window.history.replaceState(null, "", url);
      // Keep the feedback alongside the connection control rather than in the Search.
      Promise.resolve().then(() => setState(old => ({...old, message})));
    }
    void Promise.resolve().then(refresh);
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, [refresh]);

  const disconnect = useCallback(async () => {
    asked.current += 1;
    try {
      const response = await fetch(`${ROOT}/disconnect`, {method: "POST", credentials: "include"});
      if (!response.ok) {
        const error: {message: string} = await response.json();
        setState(old => ({...old, message: error.message}));
        return;
      }
      setState(old => ({...old, connected: false, message: "Spotify disconnected. Its stored tokens have been deleted."}));
    } catch {
      setState(old => ({...old, message: "Spotify could not disconnect. Try again soon."}));
    }
  }, []);

  return {...state, disconnect};
}

export const SPOTIFY_ROOT = ROOT;
