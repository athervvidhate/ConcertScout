"use client";
import { Check, Share2 } from "lucide-react";
import { useEffect, useState } from "react";

import { shareLink } from "@/lib/share";

type Props = {
  /** The link to share. A Poster not yet kept asks the API for it on the press. */
  link: () => Promise<string>;
  title: string;
  label?: string;
  /** Shows only the icon, where a Ticket's actions share one row. */
  iconOnly?: boolean;
};

const FAILED = "We could not make that link. Try again.";

export function ShareButton({ link, title, label = "Share", iconOnly }: Props) {
  const [state, setState] = useState<"idle" | "pending" | "shared" | "copied">(
    "idle",
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (state !== "shared" && state !== "copied") return;
    const timer = setTimeout(() => setState("idle"), 4000);
    return () => clearTimeout(timer);
  }, [state]);

  async function press() {
    setError(null);
    setState("pending");
    try {
      const url = await link();
      setState((await shareLink(url, title)) ?? "idle");
    } catch (caught) {
      setState("idle");
      setError(caught instanceof Error ? caught.message : FAILED);
    }
  }

  const done = state === "copied" ? "Link copied" : state === "shared" ? "Shared" : null;
  return (
    <span className="share">
      <button
        type="button"
        className={`save-action share-action${iconOnly ? " icon" : ""}`}
        aria-label={iconOnly ? (done ?? label) : undefined}
        title={iconOnly ? label : undefined}
        aria-busy={state === "pending"}
        disabled={state === "pending"}
        onClick={() => void press()}
      >
        {done ? <Check aria-hidden size={19} /> : <Share2 aria-hidden size={19} />}
        {!iconOnly && <span>{done ?? label}</span>}
      </button>
      <span role="status" className="sr-only">
        {done}
      </span>
      {error && (
        <span role="alert" className="share-error">
          {error}
        </span>
      )}
    </span>
  );
}
