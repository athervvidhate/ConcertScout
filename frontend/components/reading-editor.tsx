"use client";

import { Button } from "@base-ui/react/button";
import { Music2, Plus, X } from "lucide-react";
import { type FormEvent, type KeyboardEvent, useState } from "react";

import { dateIn, viewerZone } from "@/lib/format";
import {
  addDays,
  corrected,
  type Draft,
  draftOf,
  FURTHEST_DAYS,
} from "@/lib/reading";
import type { Reading } from "@/lib/search";

type Props = {
  reading: Reading;
  // The place a shared location stands in for when the Reading names none.
  near: boolean;
  canSearch: boolean;
  onUpdate: (reading: Reading) => void;
  onCancel: () => void;
};

/** Correct how a Search was read, then run it again without retyping it. */
export function ReadingEditor({
  reading,
  near,
  canSearch,
  onUpdate,
  onCancel,
}: Props) {
  const [draft, setDraft] = useState<Draft>(() => draftOf(reading));
  const [added, setAdded] = useState<number | null>(null);
  const today = dateIn(viewerZone(), new Date());
  const furthest = addDays(today, FURTHEST_DAYS);
  const change = (update: Partial<Draft>) =>
    setDraft((current) => ({ ...current, ...update }));

  function setArtist(index: number, name: string) {
    change({
      artists: draft.artists.map((artist, n) => (n === index ? name : artist)),
    });
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (canSearch) onUpdate(corrected(reading, draft));
  }

  function escape(event: KeyboardEvent) {
    if (event.key === "Escape") {
      event.stopPropagation();
      onCancel();
    }
  }

  return (
    <form
      className="reading-editor"
      aria-label="Change how we read your Search"
      onSubmit={submit}
      onKeyDown={escape}
    >
      <fieldset>
        <legend>Artists</legend>
        {draft.artists.map((artist, index) => (
          <div className="reading-row" key={index}>
            <input
              aria-label={`Artist ${index + 1}`}
              value={artist}
              maxLength={200}
              autoComplete="off"
              autoFocus={index === added}
              onChange={(event) => setArtist(index, event.target.value)}
            />
            <Button
              type="button"
              className="reading-remove"
              aria-label={`Remove ${artist.trim() || `Artist ${index + 1}`}`}
              onClick={() =>
                change({ artists: draft.artists.filter((_, n) => n !== index) })
              }
            >
              <X aria-hidden size={16} />
            </Button>
          </div>
        ))}
        {draft.artists.length < 20 && (
          <Button
            type="button"
            className="reading-add"
            onClick={() => {
              setAdded(draft.artists.length);
              change({ artists: [...draft.artists, ""] });
            }}
          >
            <Plus aria-hidden size={16} />
            Add an Artist
          </Button>
        )}
      </fieldset>

      <label className="reading-field">
        <span>Place</span>
        <span className="reading-row">
          <input
            value={draft.place}
            maxLength={200}
            autoComplete="off"
            placeholder={near ? "Near you" : "A city or area"}
            onChange={(event) => change({ place: event.target.value })}
          />
          {draft.place && (
            <Button
              type="button"
              className="reading-remove"
              aria-label="Clear the place"
              onClick={() => change({ place: "" })}
            >
              <X aria-hidden size={16} />
            </Button>
          )}
        </span>
      </label>

      <fieldset className="reading-dates">
        <legend>Dates</legend>
        <label>
          <span>From</span>
          <input
            type="date"
            value={draft.start}
            min={today}
            max={draft.end || furthest}
            onChange={(event) => change({ start: event.target.value })}
          />
        </label>
        <label>
          <span>To</span>
          <input
            type="date"
            value={draft.end}
            min={draft.start || today}
            max={furthest}
            onChange={(event) => change({ end: event.target.value })}
          />
        </label>
        {(draft.start || draft.end) && (
          <Button
            type="button"
            className="reading-clear"
            onClick={() => change({ start: "", end: "" })}
          >
            Any dates
          </Button>
        )}
      </fieldset>

      {draft.sound && reading.genres.length > 0 && (
        <div className="reading-field">
          <span>Sound</span>
          <span className="reading-row">
            <span className="reading-sound">
              <Music2 aria-hidden size={14} />
              {reading.genres.join(", ")}
            </span>
            <Button
              type="button"
              className="reading-remove"
              aria-label="Remove the sound"
              onClick={() => change({ sound: false })}
            >
              <X aria-hidden size={16} />
            </Button>
          </span>
        </div>
      )}

      <div className="reading-actions">
        <Button
          type="submit"
          className="reading-update"
          disabled={!canSearch}
          focusableWhenDisabled
        >
          Update Search
        </Button>
        <Button type="button" className="reading-cancel" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
