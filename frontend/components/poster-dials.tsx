"use client";

import { RotateCcw, Sparkles, Ban, X } from "lucide-react";

import {
  type DiscoveryMode,
  isDefaultSculpt,
  type SculptMeta,
  type SculptState,
} from "@/lib/sculpt";

const DISCOVERY_OPTIONS: readonly { value: DiscoveryMode; label: string }[] = [
  { value: "balanced", label: "Balanced" },
  { value: "familiar", label: "Familiar" },
  { value: "deep_cuts", label: "Deep Cuts" },
];

const BUDGET_OPTIONS: readonly { value: number | null; label: string }[] = [
  { value: null, label: "Any price" },
  { value: 40, label: "Under $40" },
  { value: 75, label: "Under $75" },
];

type DialsProps = {
  sculpt: SculptState;
  meta: SculptMeta | null;
  busy: boolean;
  onChange: (next: SculptState) => void;
};

/** Hairline-ruled editorial filter strip integrated directly into the Poster flow. */
export function PosterDials({ sculpt, meta, busy, onChange }: DialsProps) {
  const notes: string[] = [];
  if (sculpt.max_price !== null && meta && meta.unpriced_count > 0) {
    notes.push(
      meta.unpriced_count === 1
        ? "1 listing had no source price and is hidden under this cap."
        : `${meta.unpriced_count} listings had no source price and are hidden under this cap.`,
    );
  }
  if (sculpt.intimate_only && meta && meta.unknown_room_count > 0) {
    notes.push(
      meta.unknown_room_count === 1
        ? "1 venue had no verified room size and is hidden."
        : `${meta.unknown_room_count} venues had no verified room size and are hidden.`,
    );
  }

  return (
    <section
      className="poster-dials"
      aria-label="Sculpt controls"
      aria-busy={busy || undefined}
    >
      <div className="dials-row">
        <div className="dial-segment" role="group" aria-label="Discovery">
          {DISCOVERY_OPTIONS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              className="dial-btn"
              aria-pressed={sculpt.discovery === value}
              onClick={() => onChange({ ...sculpt, discovery: value })}
            >
              {label}
            </button>
          ))}
        </div>

        <span className="dial-divider" aria-hidden="true" />

        <div className="dial-segment" role="group" aria-label="Budget">
          {BUDGET_OPTIONS.map(({ value, label }) => (
            <button
              key={label}
              type="button"
              className="dial-btn"
              aria-pressed={sculpt.max_price === value}
              onClick={() => onChange({ ...sculpt, max_price: value })}
            >
              {label}
            </button>
          ))}
        </div>

        <span className="dial-divider" aria-hidden="true" />

        <div className="dial-toggles" role="group" aria-label="Poster filters">
          <button
            type="button"
            className="dial-chip"
            aria-pressed={sculpt.weekends_only}
            onClick={() =>
              onChange({ ...sculpt, weekends_only: !sculpt.weekends_only })
            }
          >
            {sculpt.weekends_only ? "Weekends only" : "Any day"}
          </button>
          <button
            type="button"
            className="dial-chip"
            aria-pressed={sculpt.intimate_only}
            onClick={() =>
              onChange({ ...sculpt, intimate_only: !sculpt.intimate_only })
            }
          >
            {sculpt.intimate_only ? "Intimate rooms" : "Any size"}
          </button>
          <button
            type="button"
            className="dial-chip"
            aria-pressed={sculpt.hide_festivals}
            onClick={() =>
              onChange({ ...sculpt, hide_festivals: !sculpt.hide_festivals })
            }
          >
            {sculpt.hide_festivals ? "Solo shows only" : "Festivals included"}
          </button>
          {busy && (
            <span className="dial-updating" role="status">
              Updating…
            </span>
          )}
        </div>
      </div>

      {notes.length > 0 && (
        <p className="dial-note" role="status">
          {notes.join(" ")}
        </p>
      )}
    </section>
  );
}

type SteeringProps = {
  sculpt: SculptState;
  busy: boolean;
  onRemove: (kind: "boost" | "exclude", artist: string) => void;
  onReset: () => void;
};

/** Active Taste steering pills and one-click Reset, aligned cleanly beside the Reading chips. */
export function SteeringPills({
  sculpt,
  busy,
  onRemove,
  onReset,
}: SteeringProps) {
  const modified = !isDefaultSculpt(sculpt);
  if (!modified) return null;

  return (
    <>
      {sculpt.boost_artists.map((artist) => (
        <button
          key={`boost-${artist}`}
          type="button"
          className="chip steer-chip"
          data-steer="boost"
          aria-busy={busy || undefined}
          aria-label={`Remove More like ${artist}`}
          onClick={() => onRemove("boost", artist)}
        >
          <span className="chip-icon">
            <Sparkles aria-hidden size={13} />
          </span>
          <span className="chip-kind">More like</span>
          {artist}
          <X aria-hidden size={13} className="steer-x" />
        </button>
      ))}
      {sculpt.exclude_artists.map((artist) => (
        <button
          key={`exclude-${artist}`}
          type="button"
          className="chip steer-chip"
          data-steer="exclude"
          aria-busy={busy || undefined}
          aria-label={`Remove Not ${artist}`}
          onClick={() => onRemove("exclude", artist)}
        >
          <span className="chip-icon">
            <Ban aria-hidden size={13} />
          </span>
          <span className="chip-kind">Not</span>
          {artist}
          <X aria-hidden size={13} className="steer-x" />
        </button>
      ))}
      <button
        type="button"
        className="reading-change steer-reset"
        onClick={onReset}
      >
        <RotateCcw aria-hidden size={13} />
        Reset
      </button>
    </>
  );
}
