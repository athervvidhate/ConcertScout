"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { unsubscribe } from "@/lib/alerts";
import { SearchRefused } from "@/lib/search";

/**
 * The page an Alert's "Stop these emails" link opens. Opening it changes nothing, because mail
 * scanners open links. The button does.
 */
export function StopAlerts() {
  const params = useSearchParams();
  const account = params.get("account") ?? "";
  const token = params.get("token") ?? "";
  const [state, setState] = useState<"ready" | "busy" | "stopped">("ready");
  const [error, setError] = useState<string | null>(null);

  async function stop() {
    setState("busy");
    setError(null);
    try {
      await unsubscribe(account, token);
      setState("stopped");
    } catch (caught) {
      setError(
        caught instanceof SearchRefused ? caught.message : "That did not work. Try again soon.",
      );
      setState("ready");
    }
  }

  if (state === "stopped") {
    return (
      <article className="account-page">
        <h1>Alerts are off</h1>
        <p role="status">
          You will get no more Alert emails. You can turn them back on from your{" "}
          <Link href="/account">account</Link>.
        </p>
      </article>
    );
  }

  return (
    <article className="account-page">
      <h1>Stop Alert emails?</h1>
      <p>Concert Scout will stop emailing you about new Concerts by Artists you follow.</p>
      <div className="account-actions">
        <button type="button" onClick={stop} disabled={state === "busy" || !account || !token}>
          Stop Alerts
        </button>
      </div>
      {error && <p role="alert">{error}</p>}
    </article>
  );
}
