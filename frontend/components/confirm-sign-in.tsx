"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type SubmitEvent, useEffect, useRef, useState } from "react";

import { AccountError, choosePassword, confirm, takeReturn } from "@/lib/account";

type Stage = "working" | "choose-password" | "failed";

/** Where Google and every emailed link land. Nothing here runs twice for one link. */
export function ConfirmSignIn() {
  const router = useRouter();
  const [stage, setStage] = useState<Stage>("working");
  const [error, setError] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const params = new URLSearchParams(window.location.search);
    // The one-use code or token leaves the address bar and history at once.
    window.history.replaceState(null, "", window.location.pathname);
    confirm(params).then(
      (confirmed) => {
        if (confirmed === "recovery") setStage("choose-password");
        else router.replace(takeReturn());
      },
      (caught: unknown) => {
        setStage("failed");
        setError(caught instanceof AccountError ? caught.message : "Sign-in is not responding.");
      },
    );
  }, [router]);

  async function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await choosePassword(password);
      router.replace(takeReturn());
    } catch (caught) {
      setError(caught instanceof AccountError ? caught.message : "That did not work. Try again.");
      setBusy(false);
    }
  }

  return (
    <article className="account-page">
      {stage === "working" && <h1>Signing you in…</h1>}
      {stage === "choose-password" && (
        <>
          <h1>Choose a new password</h1>
          <form onSubmit={submit}>
            <label>
              New password
              <input
                type="password"
                autoComplete="new-password"
                required
                minLength={8}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            <button type="submit" disabled={busy}>
              Save password
            </button>
          </form>
        </>
      )}
      {stage === "failed" && <h1>That link did not sign you in</h1>}
      {error && <p role="alert">{error}</p>}
      {stage === "failed" && (
        <p>
          <Link href="/">Back to Concert Scout</Link>, then choose Sign in from the menu to try again.
        </p>
      )}
    </article>
  );
}
