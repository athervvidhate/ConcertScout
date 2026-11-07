import { useSyncExternalStore } from "react";

const SEEN_KEY = "concert-scout-artist-hint-seen";

const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function unseen(): boolean {
  try {
    return localStorage.getItem(SEEN_KEY) === null;
  } catch {
    return false;
  }
}

/** False on the server, so the page never renders a hint a returning visitor would lose. */
export function useArtistHint(): boolean {
  return useSyncExternalStore(subscribe, unseen, () => false);
}

export function dismissArtistHint() {
  try {
    localStorage.setItem(SEEN_KEY, "1");
  } catch {
    return;
  }
  listeners.forEach((listener) => listener());
}
