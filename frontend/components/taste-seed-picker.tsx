"use client";

import { Button } from "@base-ui/react/button";
import { Plus, Upload, X } from "lucide-react";
import { type DragEvent, type KeyboardEvent, useEffect, useId, useMemo, useRef, useState } from "react";

import { SearchRefused, UNREACHABLE } from "@/lib/search";
import {
  fetchArtistSuggestions,
  fetchRelatedArtists,
  type FileTasteSource,
  addToTaste,
  replaceTasteArtists,
} from "@/lib/taste";
import {
  artistsFromPlaylistFiles,
  type ParsedPlaylistImport,
  type PlaylistExportFormat,
  TasteFileError,
} from "@/lib/taste-files";


const MAX_SEEDS = 100;
// The newest picks lead: a Search seeds from the first few, and related Artists follow them.
const RELATED_FROM = 20;
const SUGGEST_DEBOUNCE_MS = 200;
const EXPORTIFY_URL = "https://exportify.net/";
const TUNEMYMUSIC_URL = "https://www.tunemymusic.com/transfer/spotify-to-file";

const FORMAT_LABELS: Record<PlaylistExportFormat, string> = {
  exportify: "Exportify CSV",
  "tunemymusic-csv": "TuneMyMusic CSV",
  "tunemymusic-txt": "TuneMyMusic TXT",
  csv: "CSV file",
  list: "Artist list",
};

function explain(caught: unknown, fallback: string): string {
  if (caught instanceof TypeError) return UNREACHABLE;
  if (caught instanceof SearchRefused || caught instanceof TasteFileError) return caught.message;
  return fallback;
}

function artistCount(count: number): string {
  return count === 1 ? "1 Artist" : `${count} Artists`;
}

function sameArtist(a: string, b: string): boolean {
  return a.trim().toLowerCase() === b.trim().toLowerCase();
}

function progressCopy(count: number): string {
  if (count === 0) return "Pick 3 to 5 Artists you love.";
  if (count < 3) return `${artistCount(count)} picked. Add a few more.`;
  return `${artistCount(count)} picked. Save, or keep adding.`;
}

type TasteSeedPickerProps = {
  /** The Taste's whole list, to edit. Without it, the picks join the Taste. */
  initialArtists?: string[];
  onSaved?: (artists: string[]) => void;
  onCancel?: () => void;
};

export function TasteSeedPicker({ initialArtists = [], onSaved, onCancel }: TasteSeedPickerProps) {
  const inputId = useId();
  const listboxId = useId();
  const inputRef = useRef<HTMLInputElement>(null);

  const [selected, setSelected] = useState<string[]>(initialArtists);
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [suggestLoading, setSuggestLoading] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  const [related, setRelated] = useState<string[]>([]);
  const [relatedLoading, setRelatedLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trimmed = query.trim();

  // Filter out Artists already picked and offer a manual add option when the exact name is not listed.
  const options = useMemo(() => {
    const filtered = suggestions.filter(
      (name) => !selected.some((picked) => sameArtist(picked, name)),
    );
    const alreadyPicked = trimmed !== "" && selected.some((picked) => sameArtist(picked, trimmed));
    const exactMatch = trimmed !== "" && filtered.some((name) => sameArtist(name, trimmed));
    const items = filtered.map((name) => ({ name, manual: false }));
    if (trimmed && !alreadyPicked && !exactMatch) {
      items.push({ name: trimmed, manual: true });
    }
    return items;
  }, [selected, suggestions, trimmed]);

  useEffect(() => {
    if (!trimmed) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setSuggestLoading(true);
      try {
        const names = await fetchArtistSuggestions(trimmed, controller.signal);
        setSuggestions(names);
        setError(null);
      } catch (caught) {
        if (!controller.signal.aborted) {
          setSuggestions([]);
          setError(explain(caught, "Autocomplete is unavailable right now. You can still add Artists by typing."));
        }
      } finally {
        if (!controller.signal.aborted) setSuggestLoading(false);
      }
    }, SUGGEST_DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [trimmed]);

  const selectedKey = selected.slice(0, RELATED_FROM).join("\u0000");

  useEffect(() => {
    if (selected.length === 0) return;
    const controller = new AbortController();
    const names = selectedKey.split("\u0000");
    const timer = setTimeout(async () => {
      setRelatedLoading(true);
      try {
        const found = await fetchRelatedArtists(names, controller.signal);
        setRelated(found);
      } catch (caught) {
        if (!controller.signal.aborted) {
          setError(explain(caught, "Related Artists could not load right now."));
        }
      } finally {
        if (!controller.signal.aborted) setRelatedLoading(false);
      }
    }, 0);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [selected.length, selectedKey]);

  const visibleRelated = useMemo(
    () => related.filter((name) => !selected.some((picked) => sameArtist(picked, name))),
    [related, selected],
  );

  function addArtist(rawName: string, keepFocus = false) {
    const name = rawName.trim();
    if (!name) return;
    setSelected((current) => {
      if (current.length >= MAX_SEEDS || current.some((picked) => sameArtist(picked, name))) {
        return current;
      }
      return [name, ...current];
    });
    setQuery("");
    setSuggestions([]);
    setDropdownOpen(false);
    setActiveIndex(-1);
    setError(null);
    if (keepFocus) inputRef.current?.focus();
  }

  function removeArtist(artist: string) {
    setSelected((current) => {
      const next = current.filter((item) => item !== artist);
      if (next.length === 0) setRelated([]);
      return next;
    });
  }

  function onInputKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      if (options.length === 0) return;
      event.preventDefault();
      setDropdownOpen(true);
      setActiveIndex((current) => (current + 1) % options.length);
      return;
    }
    if (event.key === "ArrowUp") {
      if (options.length === 0) return;
      event.preventDefault();
      setDropdownOpen(true);
      setActiveIndex((current) => (current <= 0 ? options.length - 1 : current - 1));
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      if (dropdownOpen && activeIndex >= 0 && options[activeIndex]) {
        addArtist(options[activeIndex].name, true);
      } else if (dropdownOpen && options.length > 0) {
        addArtist(options[0].name, true);
      } else if (trimmed) {
        addArtist(trimmed, true);
      }
      return;
    }
    if (event.key === "Escape" && dropdownOpen) {
      event.preventDefault();
      event.stopPropagation();
      setDropdownOpen(false);
      setActiveIndex(-1);
    }
  }

  function save() {
    if (selected.length === 0) return;
    if (initialArtists.length > 0) replaceTasteArtists(selected);
    else addToTaste("seed", selected);
    onSaved?.(selected);
  }

  const showListbox = dropdownOpen && trimmed.length > 0 && (options.length > 0 || suggestLoading);

  return (
    <div className="taste-flow">
      <p className="taste-note">{progressCopy(selected.length)}</p>

      <div className="taste-combobox">
        <label htmlFor={inputId}>Search for an Artist</label>
        <div className="taste-input-row">
          <input
            ref={inputRef}
            id={inputId}
            type="text"
            role="combobox"
            aria-autocomplete="list"
            aria-expanded={showListbox}
            aria-controls={listboxId}
            aria-activedescendant={
              showListbox && activeIndex >= 0 ? `${listboxId}-opt-${activeIndex}` : undefined
            }
            value={query}
            onChange={(event) => {
              const next = event.target.value;
              setQuery(next);
              setActiveIndex(-1);
              if (!next.trim()) {
                setSuggestions([]);
                setDropdownOpen(false);
                setSuggestLoading(false);
              } else {
                setDropdownOpen(true);
              }
            }}
            onFocus={() => {
              if (trimmed) setDropdownOpen(true);
            }}
            onBlur={() => {
              setDropdownOpen(false);
              setActiveIndex(-1);
            }}
            onKeyDown={onInputKeyDown}
            placeholder="e.g. Khruangbin, Bonobo, Tame Impala"
            autoComplete="off"
            spellCheck={false}
            maxLength={100}
          />
          <Button
            type="button"
            className="taste-add"
            disabled={!trimmed || selected.length >= MAX_SEEDS}
            onClick={() => addArtist(trimmed, true)}
          >
            Add
          </Button>
        </div>

        {showListbox && (
          <ul id={listboxId} role="listbox" aria-label="Artist suggestions" className="taste-listbox">
            {options.map((option, index) => (
              <li
                key={`${option.manual ? "manual" : "suggest"}-${option.name}`}
                id={`${listboxId}-opt-${index}`}
                role="option"
                aria-selected={index === activeIndex}
                className="taste-option"
                data-active={index === activeIndex || undefined}
                onMouseDown={(event) => {
                  event.preventDefault();
                  addArtist(option.name, true);
                }}
              >
                <span>{option.manual ? `Add "${option.name}"` : option.name}</span>
                {option.manual && <span className="taste-option-hint">Custom</span>}
              </li>
            ))}
            {suggestLoading && options.length === 0 && (
              <li className="taste-option" role="presentation">
                <span className="taste-option-hint">Searching Artists…</span>
              </li>
            )}
          </ul>
        )}
      </div>

      {error && <p role="alert">{error}</p>}

      {selected.length > 0 && (
        <div className="taste-section" aria-live="polite">
          <div className="taste-section-head">
            <span className="taste-section-title">Your picks ({selected.length})</span>
          </div>
          <ul className="taste-chips" aria-label="Selected Artists">
            {selected.map((artist) => (
              <li key={artist} className="taste-chip">
                <span className="taste-chip-name">{artist}</span>
                <Button
                  type="button"
                  className="taste-chip-remove"
                  aria-label={`Remove ${artist}`}
                  onClick={() => removeArtist(artist)}
                >
                  <X aria-hidden size={14} />
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {selected.length > 0 && (visibleRelated.length > 0 || relatedLoading) && (
        <section className="taste-section" aria-label="Also like">
          <div className="taste-section-head">
            <span className="taste-section-title">Also like…</span>
            {relatedLoading && <span className="taste-status">Updating…</span>}
          </div>
          {visibleRelated.length > 0 && (
            <div className="taste-related">
              {visibleRelated.map((artist) => (
                <Button
                  key={artist}
                  type="button"
                  className="taste-related-chip"
                  aria-label={`Add ${artist}`}
                  onClick={() => addArtist(artist)}
                >
                  <Plus aria-hidden size={14} />
                  <span>{artist}</span>
                </Button>
              ))}
            </div>
          )}
        </section>
      )}

      <div className="taste-actions">
        <Button
          type="button"
          className="taste-primary"
          onClick={save}
          disabled={selected.length === 0}
        >
          Save Taste
        </Button>
        {onCancel && (
          <Button type="button" className="taste-secondary" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
    </div>
  );
}

type PlaylistCsvImportProps = {
  onSaved?: (artists: string[]) => void;
};

function sourceForFormat(format: PlaylistExportFormat): FileTasteSource {
  if (format === "exportify") return "exportify";
  if (format === "tunemymusic-csv" || format === "tunemymusic-txt") return "tunemymusic";
  return "csv";
}

export function PlaylistCsvImport({ onSaved }: PlaylistCsvImportProps) {
  const [dragging, setDragging] = useState(false);
  const [reading, setReading] = useState(false);
  const [parsed, setParsed] = useState<ParsedPlaylistImport | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function loadFiles(files: File[]) {
    if (files.length === 0) return;
    setReading(true);
    setError(null);
    try {
      const result = await artistsFromPlaylistFiles(files);
      setParsed(result);
      setSelected(result.artists);
    } catch (caught) {
      setParsed(null);
      setSelected([]);
      setError(explain(caught, "That file could not be read. Try another CSV or TXT export."));
    }
    setReading(false);
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragging(false);
    void loadFiles([...event.dataTransfer.files]);
  }

  function removeArtist(artist: string) {
    setSelected((current) => current.filter((item) => item !== artist));
  }

  function save() {
    if (!parsed || selected.length === 0) return;
    addToTaste(sourceForFormat(parsed.format), selected);
    onSaved?.(selected);
  }

  return (
    <div className="taste-flow">
      <p className="taste-note">
        Export a playlist or your Liked Songs with{" "}
        <a href={EXPORTIFY_URL} target="_blank" rel="noopener noreferrer">
          Exportify
        </a>{" "}
        or{" "}
        <a href={TUNEMYMUSIC_URL} target="_blank" rel="noopener noreferrer">
          TuneMyMusic
        </a>
        , then add the file here.
      </p>

      <label
        className="taste-dropzone"
        data-dragging={dragging || undefined}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <Upload aria-hidden size={22} />
        <span className="taste-dropzone-title">Drop a CSV or TXT file</span>
        <span className="taste-dropzone-sub">or click to choose one. It never leaves this device.</span>
        <input
          className="sr-only"
          type="file"
          accept=".csv,.txt,text/csv,text/plain"
          multiple
          onChange={(event) => {
            const chosen = [...(event.target.files ?? [])];
            event.target.value = "";
            void loadFiles(chosen);
          }}
        />
      </label>

      {reading && <p role="status">Reading the file…</p>}
      {error && <p role="alert">{error}</p>}

      {parsed && (
        <div className="taste-section" aria-live="polite">
          {selected.length > 0 ? (
            <>
              <p className="taste-note">
                {artistCount(selected.length)} from your {FORMAT_LABELS[parsed.format]}, most played
                first. Remove any you don&apos;t want.
              </p>
              <ul className="taste-chips" aria-label="Imported Artists">
                {selected.map((artist) => (
                  <li key={artist} className="taste-chip">
                    <span className="taste-chip-name">{artist}</span>
                    <Button
                      type="button"
                      className="taste-chip-remove"
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
            <p className="taste-note">
              All Artists removed. Restore the list or choose another file.
            </p>
          )}
          <div className="taste-actions">
            <Button
              type="button"
              className="taste-primary"
              onClick={save}
              disabled={selected.length === 0}
            >
              Save Taste
            </Button>
            {selected.length < parsed.artists.length && (
              <Button
                type="button"
                className="taste-secondary"
                onClick={() => setSelected(parsed.artists)}
              >
                Restore list
              </Button>
            )}
            <Button
              type="button"
              className="taste-secondary"
              onClick={() => {
                setParsed(null);
                setSelected([]);
                setError(null);
              }}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}

    </div>
  );
}
