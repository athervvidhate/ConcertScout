import { useEffect, useSyncExternalStore } from "react";

import { accountFetch, currentAccount, subscribeAccount, useAccount } from "@/lib/account";
import { API_URL, refusal } from "@/lib/search";

export type FollowedArtist = { artist_key: string; name: string };
export type AlertPlace = { name: string; radius_miles?: number | null };
export type Alerts = { enabled: boolean; place: AlertPlace | null; followed: FollowedArtist[] };
export const RADII = [10, 25, 50, 100] as const;

/**
 * The key two spellings of one Artist share. It mirrors the API's `names.normalize`, so the
 * Follow button knows an Artist is followed before asking. The API decides what is stored.
 */
export function artistKey(name: string): string {
  const unaccented = name.normalize("NFKD").replace(/\p{M}/gu, "");
  const words = unaccented.toLowerCase().replaceAll("&", " and ");
  const spaced = (text: string) => text.split(/\s+/u).filter(Boolean).join(" ");
  const bare = spaced(words.replace(/[^\p{L}\p{N}_\s]/gu, ""));
  // A name that is all punctuation, such as "!!!", keeps it rather than becoming empty.
  return (bare.startsWith("the ") ? bare.slice(4) : bare) || spaced(words);
}

// The signed-in Account's Alerts, shared by every Follow button and the Account page.
let alerts: Alerts | null = null;
let owner: string | null = null;
let loading: Promise<void> | null = null;
const listeners = new Set<() => void>();

function set(next: Alerts | null) {
  alerts = next;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  const stop = subscribeAccount(() => {
    const account = currentAccount();
    const id = account.status === "signed-in" ? account.id : null;
    if (id !== owner) {
      owner = id;
      loading = null;
      set(null);
    }
  });
  return () => {
    listeners.delete(listener);
    stop();
  };
}

function load(): Promise<void> {
  loading ??= accountFetch("/alerts")
    .then((response) => response.json())
    .then((read: Alerts) => set(read))
    .catch((error) => {
      loading = null;
      throw error;
    });
  return loading;
}

/** The Account's Alerts once read, or null while loading or signed out. */
export function useAlerts(): Alerts | null {
  const account = useAccount();
  const id = account.status === "signed-in" ? account.id : null;
  const read = useSyncExternalStore(subscribe, () => alerts, () => null);
  useEffect(() => {
    if (!id) return;
    owner = id;
    void load().catch(() => {});
  }, [id]);
  return id ? read : null;
}

export async function reloadAlerts(): Promise<void> {
  loading = null;
  await load();
}

export async function followArtist(name: string): Promise<void> {
  const response = await accountFetch("/followed", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
  const artist: FollowedArtist = await response.json();
  if (alerts && !alerts.followed.some((f) => f.artist_key === artist.artist_key)) {
    set({ ...alerts, followed: [...alerts.followed, artist] });
  }
}

export async function unfollowArtist(key: string): Promise<void> {
  await accountFetch(`/followed/${encodeURIComponent(key)}`, { method: "DELETE" });
  if (alerts) set({ ...alerts, followed: alerts.followed.filter((f) => f.artist_key !== key) });
}

export async function setAlertPlace(place: string, radius: number): Promise<void> {
  const response = await accountFetch("/alerts/place", {
    method: "PUT",
    body: JSON.stringify({ place, radius_miles: radius }),
  });
  const read: AlertPlace = await response.json();
  if (alerts) set({ ...alerts, place: read });
}

export async function setAlertsEnabled(enabled: boolean): Promise<void> {
  await accountFetch("/alerts/enabled", {
    method: "PUT",
    body: JSON.stringify({ enabled }),
  });
  if (alerts) set({ ...alerts, enabled });
}

/** Stops Alerts from an email's signed link, with no sign-in. */
export async function unsubscribe(account: string, token: string): Promise<void> {
  const query = new URLSearchParams({ account, token });
  const response = await fetch(`${API_URL}/alerts/unsubscribe?${query}`, { method: "POST" });
  if (!response.ok) throw await refusal(response);
}
