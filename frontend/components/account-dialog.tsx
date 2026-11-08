"use client";

import { Dialog } from "@base-ui/react/dialog";
import { X } from "lucide-react";
import { type SubmitEvent, useState } from "react";

import {
  AccountError,
  rememberReturn,
  resendConfirmation,
  sendPasswordReset,
  signIn,
  signInWithGoogle,
  signUp,
} from "@/lib/account";

type Mode = "sign-in" | "create" | "forgot" | "check-email" | "reset-sent";

const TITLES: Record<Mode, string> = {
  "sign-in": "Sign in",
  create: "Create account",
  forgot: "Reset password",
  "check-email": "Check your email",
  "reset-sent": "Check your email",
};

function explain(caught: unknown): string {
  if (caught instanceof AccountError) return caught.message;
  return "Sign-in is not responding. Try again soon.";
}

function returnHere() {
  rememberReturn(window.location.pathname + window.location.search);
}

type Props = { open: boolean; onOpenChange: (open: boolean) => void };

export function AccountDialog({ open, onOpenChange }: Props) {
  const [mode, setMode] = useState<Mode>("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resent, setResent] = useState(false);

  function show(next: Mode) {
    setMode(next);
    setError(null);
    setResent(false);
  }

  async function attempt(work: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await work();
    } catch (caught) {
      setError(explain(caught));
    }
    setBusy(false);
  }

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    void attempt(async () => {
      if (mode === "sign-in") {
        await signIn(email.trim(), password);
        setPassword("");
        onOpenChange(false);
      } else if (mode === "create") {
        returnHere();
        await signUp(email.trim(), password);
        setPassword("");
        show("check-email");
      } else {
        returnHere();
        await sendPasswordReset(email.trim());
        show("reset-sent");
      }
    });
  }

  function google() {
    void attempt(async () => {
      returnHere();
      await signInWithGoogle();
    });
  }

  function resend() {
    void attempt(async () => {
      await resendConfirmation(email.trim());
      setResent(true);
    });
  }

  const asksPassword = mode === "sign-in" || mode === "create";

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) show("sign-in");
      }}
    >
      <Dialog.Portal>
        <Dialog.Backdrop className="taste-backdrop" />
        <Dialog.Popup className="taste-panel account-panel">
          <header>
            <Dialog.Title>{TITLES[mode]}</Dialog.Title>
            <Dialog.Close className="taste-close" aria-label="Close">
              <X aria-hidden size={26} />
            </Dialog.Close>
          </header>

          {mode === "check-email" && (
            <>
              <p>
                We sent a link to <strong>{email}</strong>. Open it to finish creating your account.
              </p>
              <div className="account-actions">
                <button type="button" onClick={resend} disabled={busy || resent}>
                  {resent ? "Sent again" : "Send it again"}
                </button>
              </div>
            </>
          )}

          {mode === "reset-sent" && (
            <p>
              If <strong>{email}</strong> has an account, an email with a link to choose a new
              password is on its way.
            </p>
          )}

          {mode !== "check-email" && mode !== "reset-sent" && (
            <>
              {mode !== "forgot" && (
                <>
                  <p>Keep your Saved Concerts on every device. Searching never needs an account.</p>
                  <div className="account-actions">
                    <button type="button" onClick={google} disabled={busy}>
                      Continue with Google
                    </button>
                  </div>
                  <p className="account-or">or use your email</p>
                </>
              )}
              {mode === "forgot" && <p>We will email you a link to choose a new password.</p>}
              <form onSubmit={submit}>
                <label>
                  Email
                  <input
                    type="email"
                    autoComplete="email"
                    required
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                  />
                </label>
                {asksPassword && (
                  <label>
                    Password
                    <input
                      type="password"
                      autoComplete={mode === "create" ? "new-password" : "current-password"}
                      required
                      minLength={mode === "create" ? 8 : undefined}
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                    />
                  </label>
                )}
                <button type="submit" disabled={busy}>
                  {mode === "sign-in" ? "Sign in" : mode === "create" ? "Create account" : "Send link"}
                </button>
              </form>
            </>
          )}

          {error && <p role="alert">{error}</p>}

          <nav className="account-switch" aria-label="Other options">
            {mode !== "sign-in" && (
              <button type="button" onClick={() => show("sign-in")}>
                Sign in instead
              </button>
            )}
            {mode === "sign-in" && (
              <>
                <button type="button" onClick={() => show("create")}>
                  Create account
                </button>
                <button type="button" onClick={() => show("forgot")}>
                  Forgot password?
                </button>
              </>
            )}
          </nav>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
