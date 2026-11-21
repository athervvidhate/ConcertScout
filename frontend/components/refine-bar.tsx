"use client";

import { ExternalLink, X } from "lucide-react";

import { headlinerOf } from "@/lib/lineup";
import {
  findSourceForNote,
  type RefinementEntry,
  type UnanswerableNote,
} from "@/lib/refinement";
import type { Reading, Recommendation } from "@/lib/search";

type TrailProps = {
  trail: RefinementEntry[];
  disabled: boolean;
  onUndo: (index: number) => void;
};

/** Undoable Refinement chips rendered inline inside `.understood-row` beside the Reading chips. */
export function RefineTrail({ trail, disabled, onUndo }: TrailProps) {
  if (trail.length === 0) return null;
  return (
    <>
      {trail.map((entry, index) => (
        <button
          key={entry.id}
          type="button"
          className="chip refine-chip"
          disabled={disabled}
          aria-label={`Undo Refinement: ${entry.label}`}
          onClick={() => onUndo(index)}
        >
          <span>{entry.label}</span>
          <X aria-hidden size={13} className="refine-chip-x" />
        </button>
      ))}
    </>
  );
}

type Suggestion = { label: string; prompt: string };

function buildSuggestions(
  reading: Reading,
  recommendations: Recommendation[],
): Suggestion[] {
  const items: Suggestion[] = [];
  if (!reading.weekends_only && !reading.weekdays?.length) {
    items.push({ label: "Weekends only", prompt: "only weekends" });
  }
  if (reading.max_price === undefined) {
    items.push({ label: "Under $50", prompt: "under $50" });
  }
  const existing = new Set(reading.artists.map((a) => a.toLowerCase()));
  const firstArtist = recommendations
    .map((r) => headlinerOf(r.concert))
    .find((name): name is string => Boolean(name && !existing.has(name.toLowerCase())));
  if (firstArtist) {
    items.push({ label: `More like ${firstArtist}`, prompt: `more like ${firstArtist}` });
  }
  if (!reading.start && !reading.end) {
    items.push({ label: "Next 30 days", prompt: "in the next 30 days" });
  }
  return items.slice(0, 4);
}

type ExtrasProps = {
  reading: Reading;
  recommendations: Recommendation[];
  unanswerable: UnanswerableNote | null;
  showSuggestions: boolean;
  canRefine: boolean;
  refining: boolean;
  onRefine: (text: string) => void;
  onDismissNote: () => void;
};

/** 1-tap Refinement suggestions and inline unanswerable notes beneath the Reading chips. */
export function RefineExtras({
  reading,
  recommendations,
  unanswerable,
  showSuggestions,
  canRefine,
  refining,
  onRefine,
  onDismissNote,
}: ExtrasProps) {
  const suggestions = showSuggestions
    ? buildSuggestions(reading, recommendations)
    : [];
  const source = unanswerable
    ? findSourceForNote(unanswerable, recommendations)
    : null;

  if (suggestions.length === 0 && !unanswerable) return null;

  return (
    <div
      className="refine-extras"
      aria-label="Refine suggestions"
      aria-busy={refining || undefined}
    >
      {suggestions.length > 0 && (
        <div className="refine-suggestions" role="group" aria-label="Quick refinements">
          <span className="refine-suggest-label">Try:</span>
          {suggestions.map((item) => (
            <button
              key={item.label}
              type="button"
              className="refine-suggest-btn"
              disabled={!canRefine || refining}
              onClick={() => onRefine(item.prompt)}
            >
              {item.label}
            </button>
          ))}
        </div>
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
    </div>
  );
}
