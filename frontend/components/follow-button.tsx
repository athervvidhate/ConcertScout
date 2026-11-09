"use client";

import { Check } from "lucide-react";
import { useState } from "react";

import { AccountDialog } from "@/components/account-dialog";
import { useAccount } from "@/lib/account";
import { artistKey, followArtist, unfollowArtist, useAlerts } from "@/lib/alerts";

/** Follow an Artist to hear about their new Concerts. A guest is offered a sign-in instead. */
export function FollowButton({ name }: { name: string }) {
  const account = useAccount();
  const alerts = useAlerts();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [signingIn, setSigningIn] = useState(false);

  if (account.status === "off" || account.status === "loading") return null;
  if (account.status === "guest") {
    return (
      <>
        <button type="button" className="artist-follow" onClick={() => setSigningIn(true)}>
          Follow<span className="sr-only"> {name}</span>
        </button>
        <AccountDialog open={signingIn} onOpenChange={setSigningIn} />
      </>
    );
  }

  const key = artistKey(name);
  const following = alerts?.followed.some((f) => f.artist_key === key) ?? false;

  async function toggle() {
    setBusy(true);
    setFailed(false);
    try {
      if (following) await unfollowArtist(key);
      else await followArtist(name);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className="artist-follow"
        aria-pressed={following}
        disabled={busy || !alerts}
        onClick={toggle}
      >
        {following && <Check aria-hidden size={18} strokeWidth={3} />}
        Follow<span className="sr-only"> {name}</span>
      </button>
      {failed && <p role="alert">That did not save. Try again soon.</p>}
    </>
  );
}
