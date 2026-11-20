"use client";

import { Check, MapPin } from "lucide-react";
import { useState } from "react";

import { AccountDialog } from "@/components/account-dialog";
import { useAccount } from "@/lib/account";
import { followVenue, unfollowVenue, useAlerts } from "@/lib/alerts";
import { venueKey } from "@/lib/venues";

type FollowVenueButtonProps = {
  name: string;
  city?: string;
  lat?: number;
  lon?: number;
};

/** Follow a venue to hear about its new Concerts in daily Alerts. Guests are offered sign-in. */
export function FollowVenueButton({ name, city, lat, lon }: FollowVenueButtonProps) {
  const account = useAccount();
  const alerts = useAlerts();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [signingIn, setSigningIn] = useState(false);

  if (account.status === "off" || account.status === "loading") return null;
  if (account.status === "guest") {
    return (
      <>
        <button
          type="button"
          className="ticket-pill venue-follow"
          onClick={() => setSigningIn(true)}
        >
          <MapPin aria-hidden size={15} />
          Follow venue<span className="sr-only"> {name}</span>
        </button>
        <AccountDialog open={signingIn} onOpenChange={setSigningIn} />
      </>
    );
  }

  const key = venueKey(name, city);
  const following = alerts?.followed_venues?.some((v) => v.venue_key === key) ?? false;

  async function toggle() {
    setBusy(true);
    setFailed(false);
    try {
      if (following) await unfollowVenue(key);
      else await followVenue({ name, city, lat, lon });
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
        className="ticket-pill venue-follow"
        aria-pressed={following}
        disabled={busy || !alerts}
        onClick={toggle}
      >
        {following ? <Check aria-hidden size={15} strokeWidth={3} /> : <MapPin aria-hidden size={15} />}
        {following ? "Following venue" : "Follow venue"}
        <span className="sr-only"> {name}</span>
      </button>
      {failed && (
        <p role="alert" className="venue-follow-error">
          That did not save. Try again soon.
        </p>
      )}
    </>
  );
}
