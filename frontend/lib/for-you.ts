import { useEffect, useRef, useState } from "react";

import { accountFetch, useAccount } from "@/lib/account";
import { viewerZone } from "@/lib/format";
import type { Place } from "@/lib/place";
import { API_URL, type Concert, refusal } from "@/lib/search";
import {
  type ImportedTaste,
  keepTaste,
  readTaste,
  type TasteSource,
  useImportedTaste,
} from "@/lib/taste";

export type ForYouSignal = "seed" | "one_hop" | "co_billed";
export type ForYouItem = {
  concert: Concert;
  artist: string;
  signal: ForYouSignal;
  via: string;
};
export type ForYou = { place: string; concerts: ForYouItem[] };

/** The API's answer when a signed-in Account has no browser location and no Alert place. */
export const NEEDS_PLACE = "for_you_needs_place";

/** An Account's saved Taste, as the API returns it. */
export type TasteProfile = {
  source: TasteSource;
  artists: string[];
  updated_at: string;
};

// The Account's profile holds at most this many names, favourites first.
const MAX_SYNCED = 100;

/** Why a Concert is on the shelf, from the source's own Lineup and the Taste's own Artists. */
export function noteFor({
  signal,
  via,
}: Pick<ForYouItem, "signal" | "via">): string {
  if (signal === "seed") return "An Artist in your Taste";
  if (signal === "one_hop") return `Similar to ${via}`;
  return `Often on the same bill as ${via}`;
}

export function shelfTitle(place: string): string {
  // A browser location has no name, so the API calls it "Near you".
  return `For You near ${place === "Near you" ? "you" : place.split(",")[0]}`;
}

function signature(
  taste: Pick<ImportedTaste, "source" | "artists"> | null,
): string {
  return taste ? `${taste.source}\n${taste.artists.join("\n")}` : "";
}

/** Which side holds the newer Taste when this device and the Account disagree. */
export function reconcile(
  local: ImportedTaste | null,
  remote: TasteProfile | null,
): "pull" | "push" | "none" {
  if (!remote) return local ? "push" : "none";
  if (!local) return "pull";
  if (signature(local) === signature(remote)) return "none";
  const savedHere = Date.parse(local.importedAt ?? "") || 0;
  return Date.parse(remote.updated_at) > savedHere ? "pull" : "push";
}

async function readProfile(): Promise<TasteProfile | null> {
  return (await accountFetch("/taste")).json();
}

async function writeProfile(taste: ImportedTaste): Promise<void> {
  await accountFetch("/taste", {
    method: "PUT",
    body: JSON.stringify({
      source: taste.source,
      artists: taste.artists.slice(0, MAX_SYNCED),
    }),
  });
}

/**
 * Keeps a signed-in Account's Taste Profile and this device's Taste the same. The newer one wins
 * when someone signs in, and a change or a clear on this device follows to the Account.
 * Returns true once the shelf may ask for a signed-in person, and always for a guest.
 */
export function useTasteSync(): boolean {
  const account = useAccount();
  const taste = useImportedTaste();
  const id = account.status === "signed-in" ? account.id : null;
  const [reconciled, setReconciled] = useState<string | null>(null);
  // What the Account is known to hold, so a pull is never pushed straight back.
  const known = useRef("");

  useEffect(() => {
    if (!id) return;
    let live = true;
    void (async () => {
      const remote = await readProfile();
      if (!live) return;
      const local = readTaste();
      const side = reconcile(local, remote);
      if (side === "pull" && remote) {
        known.current = signature(remote);
        keepTaste({
          source: remote.source,
          artists: remote.artists,
          importedAt: remote.updated_at,
        });
      } else if (side === "push" && local) {
        await writeProfile(local);
        known.current = signature(local);
      } else {
        known.current = signature(remote);
      }
      if (live) setReconciled(id);
    })().catch(() => {});
    return () => {
      live = false;
    };
  }, [id]);

  const ready = id !== null && reconciled === id;
  const now = signature(taste);
  useEffect(() => {
    if (!ready || now === known.current) return;
    const before = known.current;
    known.current = now;
    const change = taste
      ? writeProfile(taste)
      : accountFetch("/taste", { method: "DELETE" });
    // A failed sync is tried again by the next change, so the device never loses its own Taste.
    void change.catch(() => {
      if (known.current === now) known.current = before;
    });
  }, [ready, now, taste]);

  return id === null || ready;
}

export async function fetchForYou(
  taste: ImportedTaste,
  place: Place | null,
  signedIn: boolean,
  signal: AbortSignal,
): Promise<ForYou> {
  const near = place ? { lat: place.lat, lon: place.lon } : undefined;
  const time_zone = viewerZone();
  if (signedIn) {
    // The API reads the Account's own Taste Profile, so none is sent.
    const response = await accountFetch("/for-you", {
      method: "POST",
      body: JSON.stringify({ near, time_zone }),
      signal,
    });
    return response.json();
  }
  const response = await fetch(`${API_URL}/for-you`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      artists: taste.artists.slice(0, MAX_SYNCED),
      near,
      time_zone,
    }),
    signal,
  });
  if (!response.ok) throw await refusal(response);
  return response.json();
}
