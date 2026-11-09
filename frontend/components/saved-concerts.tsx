"use client";

import { Button } from "@base-ui/react/button";
import { X } from "lucide-react";
import { useState, useSyncExternalStore } from "react";

import { AccountDialog } from "@/components/account-dialog";
import { MovedSaves } from "@/components/moved-saves";
import { Ticket } from "@/components/ticket";
import { useAccount } from "@/lib/account";
import { removeSaved, upcoming, useSavedConcerts } from "@/lib/saved";

const noSubscription = () => () => {};
const MINUTE = 60_000;
const thisMinute = () => Math.floor(Date.now() / MINUTE);

function SignInPrompt() {
  const [open, setOpen] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;
  return (
    <section className="account-offer" aria-label="Sync your Saved Concerts">
      <p>These saves stay on this device. Sign in to move them into an account and keep them on every device.</p>
      <div className="account-actions">
        <button type="button" onClick={() => setOpen(true)}>
          Sign in
        </button>
        <button type="button" onClick={() => setDismissed(true)}>
          Not now
        </button>
      </div>
      <AccountDialog open={open} onOpenChange={setOpen} />
    </section>
  );
}

export function SavedConcerts() {
  const account = useAccount();
  const { status, saved } = useSavedConcerts();
  const minute = useSyncExternalStore(noSubscription, thisMinute, () => 0);
  const [error, setError] = useState<string | null>(null);
  const concerts = upcoming(saved, new Date(minute * MINUTE));

  async function remove(id: string) {
    setError(null);
    try {
      await removeSaved(id);
    } catch {
      setError("Your account did not remove that Concert. Try again.");
    }
  }

  let body;
  if (status === "loading") body = <p className="saved-empty">Loading your Saved Concerts…</p>;
  else if (status === "failed") {
    body = <p className="saved-empty">Your account is not responding. Try again soon.</p>;
  } else if (concerts.length === 0) {
    body = <p className="saved-empty">Nothing saved yet. Save a Concert from a Poster.</p>;
  } else {
    body = (
      <ul className="saved-list">
        {concerts.map((recommendation, rank) => (
          <li key={recommendation.concert.id}>
            <Ticket recommendation={recommendation} rank={rank} />
            <Button
              type="button"
              className="saved-remove"
              onClick={() => remove(recommendation.concert.id)}
            >
              <X aria-hidden size={22} />
              <span>Remove</span>
            </Button>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <>
      {account.status === "guest" && <SignInPrompt />}
      <MovedSaves />
      {error && (
        <p className="account-note" role="alert">
          {error}
        </p>
      )}
      {body}
    </>
  );
}
