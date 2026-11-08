import { useMemo, useSyncExternalStore } from "react";

import { accountFetch, currentAccount, subscribeAccount } from "@/lib/account";
import { dateIn, viewerZone } from "@/lib/format";
import type { Recommendation } from "@/lib/search";

const SAVED_KEY = "concert-scout-saved";
const SKIPPED_KEY = "concert-scout-skipped";
const EMPTY = "[]";

export type Decision = "saved" | "skipped";

/**
 * Saved Concerts live on the device for a guest and in the account once signed in. The two never
 * mix: signing in moves the device's saves into the account, signed-in views read only the
 * account, and signing out never copies the account back to the device.
 * Skips always stay on the device.
 */
export type SavedView = {
  where: "device" | "account";
  status: "loading" | "ready" | "failed";
  saved: Recommendation[];
  // Guest saves this sign-in moved into the account, and those still left on the device.
  moved?: Moved;
};

export type Moved = { added: number; left: number };

type AccountSaves = SavedView & { owner: string };

const listeners = new Set<() => void>();
let account: AccountSaves | null = null;
let following = false;

function notify() {
  listeners.forEach((listener) => listener());
}

function setAccount(next: AccountSaves | null) {
  account = next;
  notify();
}

// A new owner means a sign-in, sign-out or switch, so nothing of the last account is kept.
function followAccount() {
  const state = currentAccount();
  const owner = state.status === "signed-in" ? state.id : null;
  if ((account?.owner ?? null) === owner) return;
  setAccount(owner ? { owner, where: "account", status: "loading", saved: [] } : null);
  if (owner) void loadAccount(owner);
}

/**
 * Signing in moves this device's guest saves into the account. Each one leaves the device only
 * once the account holds it, so a failed or repeated move loses and duplicates nothing, and the
 * next sign-in tries what is left.
 */
async function moveDeviceSaves(): Promise<Moved | undefined> {
  const device = readList<Recommendation>(SAVED_KEY);
  if (device.length === 0) return undefined;
  try {
    const saves = device.map(({ concert, reason }) => ({ concert_id: concert.id, reason }));
    const response = await accountFetch("/saved/import", {
      method: "POST",
      body: JSON.stringify({ saves }),
    });
    const result: { saved: Recommendation[] } = await response.json();
    const added = new Set(result.saved.map((r) => r.concert.id));
    writeDevice(
      readList<Recommendation>(SAVED_KEY).filter((r) => !added.has(r.concert.id)),
      readList(SKIPPED_KEY),
    );
    return { added: added.size, left: device.length - added.size };
  } catch {
    return { added: 0, left: device.length };
  }
}

async function loadAccount(owner: string) {
  try {
    const moved = await moveDeviceSaves();
    const response = await accountFetch("/saved");
    const saved: Recommendation[] = await response.json();
    if (account?.owner === owner) setAccount({ ...account, status: "ready", saved, moved });
  } catch {
    if (account?.owner === owner) setAccount({ ...account, status: "failed" });
  }
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  if (!following) {
    following = true;
    subscribeAccount(followAccount);
    followAccount();
  }
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

function parseList<T>(raw: string): T[] {
  try {
    const list: unknown = JSON.parse(raw);
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

function readList<T>(key: string): T[] {
  return parseList(localStorage.getItem(key) ?? EMPTY);
}

function writeDevice(saved: Recommendation[], skipped: string[]) {
  localStorage.setItem(SAVED_KEY, JSON.stringify(saved));
  localStorage.setItem(SKIPPED_KEY, JSON.stringify(skipped));
  notify();
}

function withoutSkip(id: string) {
  const skipped = readList<string>(SKIPPED_KEY);
  if (skipped.includes(id)) writeDevice(readList(SAVED_KEY), skipped.filter((s) => s !== id));
}

function accountSaves(): AccountSaves | null {
  return currentAccount().status === "signed-in" ? account : null;
}

export type Saving = { where: "device" } | { where: "account"; done: Promise<void> };

/**
 * A device save throws at once when the browser refuses storage. An account save shows at once
 * and `done` rejects if the account did not keep it, after taking it back off the list.
 */
export function saveConcert(recommendation: Recommendation): Saving {
  const id = recommendation.concert.id;
  const signedIn = accountSaves();
  if (!signedIn) {
    const others = readList<Recommendation>(SAVED_KEY).filter((r) => r.concert.id !== id);
    const skipped = readList<string>(SKIPPED_KEY).filter((skippedId) => skippedId !== id);
    writeDevice([...others, recommendation], skipped);
    return { where: "device" };
  }
  const { owner } = signedIn;
  const without = (list: Recommendation[]) => list.filter((r) => r.concert.id !== id);
  setAccount({ ...signedIn, saved: [...without(signedIn.saved), recommendation] });
  const done = (async () => {
    try {
      withoutSkip(id);
      const response = await accountFetch(`/saved/${encodeURIComponent(id)}`, {
        method: "PUT",
        body: JSON.stringify({ reason: recommendation.reason }),
      });
      const kept: Recommendation = await response.json();
      if (account?.owner === owner) {
        setAccount({ ...account, saved: account.saved.map((r) => (r.concert.id === id ? kept : r)) });
      }
    } catch (caught) {
      if (account?.owner === owner) setAccount({ ...account, saved: without(account.saved) });
      throw caught;
    }
  })();
  return { where: "account", done };
}

export function skipConcert(id: string): void {
  const signedIn = accountSaves();
  const saved = readList<Recommendation>(SAVED_KEY).filter((r) => r.concert.id !== id);
  const skipped = readList<string>(SKIPPED_KEY).filter((skippedId) => skippedId !== id);
  writeDevice(signedIn ? readList(SAVED_KEY) : saved, [...skipped, id]);
  if (signedIn?.saved.some((r) => r.concert.id === id)) void removeSaved(id).catch(() => {});
}

/** Rejects, with the Concert back in place, when the account could not remove it. */
export async function removeSaved(id: string): Promise<void> {
  const signedIn = accountSaves();
  if (!signedIn) {
    const saved = readList<Recommendation>(SAVED_KEY).filter((r) => r.concert.id !== id);
    writeDevice(saved, readList<string>(SKIPPED_KEY));
    return;
  }
  const { owner, saved: before } = signedIn;
  setAccount({ ...signedIn, saved: before.filter((r) => r.concert.id !== id) });
  try {
    await accountFetch(`/saved/${encodeURIComponent(id)}`, { method: "DELETE" });
  } catch (caught) {
    if (account?.owner === owner) setAccount({ ...account, saved: before });
    throw caught;
  }
}

function useStored(key: string): string {
  return useSyncExternalStore(
    subscribe,
    () => localStorage.getItem(key) ?? EMPTY,
    () => EMPTY,
  );
}

function useAccountSaves(): AccountSaves | null | "unknown" {
  return useSyncExternalStore(
    subscribe,
    () => {
      const state = currentAccount();
      if (state.status === "loading") return "unknown";
      if (state.status !== "signed-in") return null;
      return account?.owner === state.id ? account : "unknown";
    },
    () => "unknown",
  );
}

function useDeviceSaves(): Recommendation[] {
  const raw = useStored(SAVED_KEY);
  return useMemo(() => parseList<Recommendation>(raw), [raw]);
}

const UNKNOWN: SavedView = { where: "device", status: "loading", saved: [] };

export function useSavedConcerts(): SavedView {
  const device = useDeviceSaves();
  const signedIn = useAccountSaves();
  return useMemo(() => {
    if (signedIn === "unknown") return UNKNOWN;
    return signedIn ?? { where: "device", status: "ready", saved: device };
  }, [device, signedIn]);
}

export function useDecisions(): Record<string, Decision> {
  const { saved } = useSavedConcerts();
  const rawSkipped = useStored(SKIPPED_KEY);
  return useMemo(() => {
    const skipped = parseList<string>(rawSkipped).map((id) => [id, "skipped" as const]);
    const kept = saved.map((r) => [r.concert.id, "saved" as const]);
    return Object.fromEntries([...skipped, ...kept]);
  }, [saved, rawSkipped]);
}

/** A Concert with no known date stays, because it may still be ahead. */
export function upcoming(saved: Recommendation[], now: Date): Recommendation[] {
  return saved.filter(({ concert }) => !concert.date || concert.date >= dateIn(concert.time_zone ?? viewerZone(), now));
}
