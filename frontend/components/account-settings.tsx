"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AccountDialog } from "@/components/account-dialog";
import { MovedSaves } from "@/components/moved-saves";
import { deleteAccount, signOut, useAccount } from "@/lib/account";
import { SearchRefused } from "@/lib/search";

const METHOD_NAMES: Record<string, string> = { email: "Email and password", google: "Google" };

export function AccountSettings() {
  const router = useRouter();
  const account = useAccount();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [signingIn, setSigningIn] = useState(false);
  const [mustSignIn, setMustSignIn] = useState(false);

  if (account.status === "loading") return <h1>Account</h1>;
  if (account.status !== "signed-in") {
    return (
      <article className="account-page">
        <h1>Account</h1>
        <p>You are not signed in. Searching and saving on this device never need an account.</p>
        {account.status === "guest" && (
          <div className="account-actions">
            <button type="button" onClick={() => setSigningIn(true)}>
              Sign in
            </button>
          </div>
        )}
        <AccountDialog open={signingIn} onOpenChange={setSigningIn} />
      </article>
    );
  }

  async function leave() {
    setBusy(true);
    await signOut();
    router.replace("/");
  }

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      await deleteAccount();
      router.replace("/");
    } catch (caught) {
      const refused = caught instanceof SearchRefused;
      setMustSignIn(refused && caught.code === "sign_in_again");
      setError(refused ? caught.message : "Your account is not responding. Try again soon.");
      setBusy(false);
    }
  }

  return (
    <article className="account-page">
      <h1>Account</h1>
      <p>
        Signed in as <strong>{account.email}</strong> with{" "}
        {account.methods.map((method) => METHOD_NAMES[method] ?? method).join(" and ")}.
      </p>
      <p>
        Your <Link href="/saved">Saved Concerts</Link> follow this account to every device you sign
        in on. Your Taste and any Spotify connection stay on each device for now.
      </p>
      <MovedSaves />
      <div className="account-actions">
        <button type="button" onClick={leave} disabled={busy}>
          Sign out
        </button>
      </div>

      <h2>Delete account</h2>
      <p>
        This deletes your account and its Saved Concerts for good. Saves still on this device stay
        until you remove them.
      </p>
      {!confirming ? (
        <div className="account-actions">
          <button type="button" onClick={() => setConfirming(true)} disabled={busy}>
            Delete account
          </button>
        </div>
      ) : (
        <div className="account-actions">
          <button type="button" className="account-danger" onClick={remove} disabled={busy}>
            Yes, delete my account
          </button>
          <button type="button" onClick={() => setConfirming(false)} disabled={busy}>
            Keep it
          </button>
        </div>
      )}
      {error && <p role="alert">{error}</p>}
      {mustSignIn && (
        <div className="account-actions">
          <button type="button" onClick={() => setSigningIn(true)}>
            Sign in again
          </button>
        </div>
      )}
      <AccountDialog
        open={signingIn}
        onOpenChange={(open) => {
          setSigningIn(open);
          if (!open) {
            setMustSignIn(false);
            setError(null);
          }
        }}
      />
    </article>
  );
}
