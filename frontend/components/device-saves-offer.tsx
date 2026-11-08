"use client";

import { useState } from "react";

import { useAccount } from "@/lib/account";
import { countOf } from "@/lib/format";
import { SearchRefused } from "@/lib/search";
import { forgetDeviceSaves, importDeviceSaves, useDeviceSaves } from "@/lib/saved";

/**
 * After sign-in, the device's guest saves stay put until the person chooses. A shared browser can
 * hold someone else's saves, so nothing moves into an account on its own.
 */
export function DeviceSavesOffer() {
  const account = useAccount();
  const device = useDeviceSaves();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [kept, setKept] = useState(false);

  if (account.status !== "signed-in") return null;
  if (device.length === 0 || kept) {
    return result ? (
      <p className="account-note" role="status">
        {result}
      </p>
    ) : null;
  }

  async function add() {
    setBusy(true);
    try {
      const { added, failed } = await importDeviceSaves();
      const missing = failed.length
        ? ` ${countOf(failed.length, "Concert")} could not be confirmed with Ticketmaster and stayed on this device.`
        : "";
      setResult(`Added ${countOf(added, "Concert")} to your account.${missing}`);
    } catch (caught) {
      setResult(
        caught instanceof SearchRefused
          ? caught.message
          : "Your account is not responding. Your saves are still on this device.",
      );
    }
    setBusy(false);
  }

  function forget() {
    forgetDeviceSaves();
    setResult("Removed this device's saves.");
  }

  return (
    <section className="account-offer" aria-label="This device's Saved Concerts">
      <p>
        This device has {countOf(device.length, "Saved Concert")} from before you signed in. Add
        them to your account?
      </p>
      <div className="account-actions">
        <button type="button" onClick={add} disabled={busy}>
          Add to my account
        </button>
        <button type="button" onClick={() => setKept(true)} disabled={busy}>
          Keep on this device
        </button>
        <button type="button" onClick={forget} disabled={busy}>
          Remove from this device
        </button>
      </div>
      {result && <p role="status">{result}</p>}
    </section>
  );
}
