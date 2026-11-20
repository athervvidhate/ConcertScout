"use client";

import { Button } from "@base-ui/react/button";
import { X } from "lucide-react";
import { type FormEvent, useState } from "react";

import { SearchRefused, UNREACHABLE } from "@/lib/search";
import { fetchYouTubePlaylistTaste, keepTaste } from "@/lib/taste";

import styles from "./youtube-import.module.css";

const UNREADABLE = "That playlist could not be read. Try again.";

function explain(caught: unknown): string {
  if (caught instanceof TypeError) return UNREACHABLE;
  if (caught instanceof SearchRefused) return caught.message;
  return UNREADABLE;
}

function artistCount(count: number): string {
  return count === 1 ? "1 Artist" : `${count} Artists`;
}

type YouTubeImportProps = {
  onSaved?: (artists: string[]) => void;
};

export function YouTubeImport({ onSaved }: YouTubeImportProps) {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [extracted, setExtracted] = useState<string[] | null>(null);
  const [selected, setSelected] = useState<string[]>([]);

  const trimmed = url.trim();

  async function findArtists(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    try {
      const artists = await fetchYouTubePlaylistTaste(trimmed);
      setExtracted(artists);
      setSelected(artists);
    } catch (caught) {
      setExtracted(null);
      setSelected([]);
      setError(explain(caught));
    }
    setLoading(false);
  }

  function removeArtist(artist: string) {
    setSelected((current) => current.filter((item) => item !== artist));
  }

  function save() {
    if (selected.length === 0) return;
    keepTaste({ source: "youtube", artists: selected });
    onSaved?.(selected);
  }

  function resetDraft() {
    setExtracted(null);
    setSelected([]);
    setError(null);
  }

  return (
    <div className={styles.root}>
      <form onSubmit={findArtists} noValidate>
        <label>
          YouTube playlist URL
          <input
            type="text"
            inputMode="url"
            value={url}
            onChange={(event) => {
              setUrl(event.target.value);
              if (error) setError(null);
            }}
            placeholder="https://www.youtube.com/playlist?list=..."
            autoComplete="off"
            spellCheck={false}
            maxLength={2048}
          />
        </label>
        <p className={styles.hint}>
          Paste a public or unlisted YouTube or YouTube Music playlist link. Only the Artist names
          you save stay on this device.
        </p>
        <Button type="submit" disabled={loading || !trimmed}>
          {loading ? "Reading playlist" : "Find Artists"}
        </Button>
        {error && <p role="alert">{error}</p>}
      </form>

      {extracted && (
        <div className={styles.review} aria-live="polite">
          {selected.length > 0 ? (
            <>
              <p className={styles.summary}>
                Found {artistCount(selected.length)}. Remove any that don&apos;t belong, then save.
              </p>
              <ul className={styles.chips} aria-label="Extracted Artists">
                {selected.map((artist) => (
                  <li key={artist} className={styles.chip}>
                    <span className={styles.chipName}>{artist}</span>
                    <Button
                      type="button"
                      className={styles.chipRemove}
                      aria-label={`Remove ${artist}`}
                      onClick={() => removeArtist(artist)}
                    >
                      <X aria-hidden size={14} />
                    </Button>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className={styles.summary}>
              All Artists removed. Restore the list or paste another playlist link.
            </p>
          )}
          <div className={styles.actions}>
            <Button
              type="button"
              className={styles.primary}
              onClick={save}
              disabled={selected.length === 0}
            >
              Save Taste
            </Button>
            {selected.length < extracted.length && (
              <Button
                type="button"
                className={styles.secondary}
                onClick={() => setSelected(extracted)}
              >
                Restore list
              </Button>
            )}
            <Button type="button" className={styles.secondary} onClick={resetDraft}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
