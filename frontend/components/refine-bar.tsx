"use client";

import { ArrowRight, ExternalLink, X } from "lucide-react";
import { type FormEvent, useState } from "react";

import {
  findSourceForNote,
  MAX_REFINEMENT_CHARS,
  type RefinementEntry,
  type UnanswerableNote,
} from "@/lib/refinement";
import type { Recommendation } from "@/lib/search";

type Props = {
  trail: RefinementEntry[];
  unanswerable: UnanswerableNote | null;
  recommendations: Recommendation[];
  canRefine: boolean;
  refining: boolean;
  onRefine: (text: string) => void;
  onUndo: (index: number) => void;
  onDismissNote: () => void;
};

/** Typed Refinement input under the Poster, with a horizontal trail of undoable chips above it. */
export function RefineBar({
  trail,
  unanswerable,
  recommendations,
  canRefine,
  refining,
  onRefine,
  onUndo,
  onDismissNote,
}: Props) {
  const [draft, setDraft] = useState("");
  const source = unanswerable
    ? findSourceForNote(unanswerable, recommendations)
    : null;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = draft.trim();
    if (!trimmed || !canRefine || refining) return;
    onRefine(trimmed);
    setDraft("");
  }

  return (
    <section
      className="refine-bar"
      aria-label="Refine Search"
      aria-busy={refining || undefined}
    >
      {trail.length > 0 && (
        <ul className="refine-trail" aria-label="Applied Refinements">
          {trail.map((entry, index) => (
            <li key={entry.id}>
              <button
                type="button"
                className="chip refine-chip"
                disabled={!canRefine || refining}
                aria-label={`Undo Refinement: ${entry.label}`}
                onClick={() => onUndo(index)}
              >
                <span>{entry.label}</span>
                <X aria-hidden size={13} className="refine-chip-x" />
              </button>
            </li>
          ))}
        </ul>
      )}

      {unanswerable && (
        <div className="refine-note" role="status">
          <div className="refine-note-body">
            <p>{unanswerable.message}</p>
            {source && (
              <a
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="refine-source-link"
              >
                Check {source.label} listing
                <ExternalLink aria-hidden size={13} />
              </a>
            )}
          </div>
          <button
            type="button"
            className="refine-note-close"
            aria-label="Dismiss note"
            onClick={onDismissNote}
          >
            <X aria-hidden size={15} />
          </button>
        </div>
      )}

      <form className="refine-form" onSubmit={submit}>
        <label htmlFor="refine-input" className="sr-only">
          Refine this Poster
        </label>
        <input
          id="refine-input"
          type="text"
          className="refine-input"
          value={draft}
          maxLength={MAX_REFINEMENT_CHARS}
          disabled={refining}
          placeholder="Try: only Saturdays, cheaper, try Oakland, more like #2…"
          onChange={(event) => setDraft(event.target.value)}
        />
        <button
          type="submit"
          className="refine-submit"
          disabled={!canRefine || refining || !draft.trim()}
        >
          <span>{refining ? "Refining…" : "Refine"}</span>
          <ArrowRight aria-hidden size={16} />
        </button>
      </form>
    </section>
  );
}
