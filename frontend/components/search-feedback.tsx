"use client";

import { Button } from "@base-ui/react/button";
import { type SubmitEvent, useState } from "react";

import { sendReport } from "@/lib/feedback";
import { type Interpreted, type Recommendation, SearchRefused } from "@/lib/search";

type Props = {
  search: string;
  interpreted: Interpreted | null;
  recommendations: Recommendation[];
  error: string | null;
};

export function SearchFeedback({ search, interpreted, recommendations, error }: Props) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setSending(true);
    setFailure(null);
    try {
      await sendReport({ search, note, interpreted, recommendations, error });
      setSent(true);
    } catch (caught) {
      setFailure(caught instanceof SearchRefused ? caught.message : "That did not send. Try again soon.");
    }
    setSending(false);
  }

  if (sent) {
    return (
      <section className="search-feedback" aria-label="Report this Search">
        <p role="status">Thanks. We got your report.</p>
      </section>
    );
  }

  return (
    <section className="search-feedback" aria-label="Report this Search">
      <p>
        Didn&apos;t find what you wanted?{" "}
        <Button type="button" aria-expanded={open} onClick={() => setOpen(!open)}>
          Tell us
        </Button>
      </p>
      {open && (
        <form onSubmit={submit}>
          <label>
            What were you hoping for? (optional)
            <textarea
              value={note}
              onChange={(event) => setNote(event.target.value)}
              rows={3}
              maxLength={1000}
            />
          </label>
          <p>We&apos;ll send this note with your Search and its results.</p>
          <Button type="submit" disabled={sending}>
            {sending ? "Sending" : "Send report"}
          </Button>
          {failure && <p role="alert">{failure}</p>}
        </form>
      )}
    </section>
  );
}
