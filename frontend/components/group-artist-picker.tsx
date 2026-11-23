"use client";

import { Plus, Sparkles, X } from "lucide-react";
import { type KeyboardEvent, useEffect, useId, useMemo, useRef, useState } from "react";

import {
  MAX_GROUP_TASTE,
  QUICK_PICK_ARTISTS,
  mergeArtists,
  parseArtistsInput,
} from "@/lib/group-scout";
import { fetchArtistSuggestions, fetchRelatedArtists, useImportedTaste } from "@/lib/taste";

const SUGGEST_DEBOUNCE_MS = 200;
const RELATED_FROM = 20;

function sameArtist(a: string, b: string): boolean {
  return a.trim().toLowerCase() === b.trim().toLowerCase();
}

type Props = {
  id: string;
  label: string;
  artists: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
};

/**
 * Live Artist picker for Group Scout, using the same `/suggest` autocomplete and cascading
 * related-Artist recommendations as the main app's Taste Seed picker.
 */
export function GroupArtistPicker({
  id,
  label,
  artists,
  onChange,
  placeholder = "Search or paste Artists (e.g. Khruangbin, Bonobo)",
}: Props) {
  const savedTaste = useImportedTaste();
  const listboxId = useId();
  const inputRef = useRef<HTMLInputElement>(null);

  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [suggestLoading, setSuggestLoading] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [related, setRelated] = useState<string[]>([]);
  const [relatedLoading, setRelatedLoading] = useState(false);

  const trimmed = query.trim();

  const options = useMemo(() => {
    const activeSuggestions = trimmed ? suggestions : [];
    const filtered = activeSuggestions.filter(
      (name) => !artists.some((picked) => sameArtist(picked, name)),
    );
    const alreadyPicked =
      trimmed !== "" && artists.some((picked) => sameArtist(picked, trimmed));
    const exactMatch =
      trimmed !== "" && filtered.some((name) => sameArtist(name, trimmed));
    const items = filtered.map((name) => ({ name, manual: false }));
    if (trimmed && !alreadyPicked && !exactMatch) {
      items.push({ name: trimmed, manual: true });
    }
    return items;
  }, [artists, suggestions, trimmed]);

  useEffect(() => {
    if (!trimmed) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setSuggestLoading(true);
      try {
        const names = await fetchArtistSuggestions(trimmed, controller.signal);
        if (!controller.signal.aborted) setSuggestions(names);
      } catch {
        if (!controller.signal.aborted) setSuggestions([]);
      } finally {
        if (!controller.signal.aborted) setSuggestLoading(false);
      }
    }, SUGGEST_DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [trimmed]);

  const selectedKey = artists.slice(0, RELATED_FROM).join("\u0000");

  useEffect(() => {
    if (artists.length === 0) return;
    const controller = new AbortController();
    const names = selectedKey.split("\u0000").filter(Boolean);
    const timer = setTimeout(async () => {
      setRelatedLoading(true);
      try {
        const found = await fetchRelatedArtists(names, controller.signal);
        if (!controller.signal.aborted) setRelated(found);
      } catch {
        if (!controller.signal.aborted) setRelated([]);
      } finally {
        if (!controller.signal.aborted) setRelatedLoading(false);
      }
    }, 0);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [artists.length, selectedKey]);

  const visibleRelated = useMemo(
    () =>
      artists.length === 0
        ? []
        : related.filter((name) => !artists.some((picked) => sameArtist(picked, name))),
    [artists, related],
  );

  function addNames(names: string[]) {
    if (names.length === 0 || artists.length >= MAX_GROUP_TASTE) return;
    // Place newly picked Artists at the front so related-Artist suggestions cascade from them.
    onChange(mergeArtists(names, artists));
  }

  function pickOne(name: string) {
    const parsed = parseArtistsInput(name);
    if (parsed.length === 0) return;
    addNames(parsed);
    setQuery("");
    setSuggestions([]);
    setDropdownOpen(false);
    setActiveIndex(-1);
    inputRef.current?.focus();
  }

  function addTyped() {
    const parsed = parseArtistsInput(query);
    if (parsed.length === 0) return;
    addNames(parsed);
    setQuery("");
    setSuggestions([]);
    setDropdownOpen(false);
    setActiveIndex(-1);
  }

  function removeArtist(name: string) {
    onChange(artists.filter((item) => !sameArtist(item, name)));
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      if (options.length === 0) return;
      event.preventDefault();
      setDropdownOpen(true);
      setActiveIndex((prev) => (prev + 1) % options.length);
    } else if (event.key === "ArrowUp") {
      if (options.length === 0) return;
      event.preventDefault();
      setDropdownOpen(true);
      setActiveIndex((prev) => (prev <= 0 ? options.length - 1 : prev - 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (dropdownOpen && activeIndex >= 0 && options[activeIndex]) {
        pickOne(options[activeIndex].name);
      } else {
        addTyped();
      }
    } else if (event.key === "Escape") {
      setDropdownOpen(false);
      setActiveIndex(-1);
    }
  }

  const showMenu = dropdownOpen && trimmed !== "" && (options.length > 0 || suggestLoading);

  return (
    <div className="group-taste-block">
      <div className="group-taste-head">
        <label htmlFor={id}>{label}</label>
        {savedTaste && savedTaste.artists.length > 0 && (
          <button
            type="button"
            className="group-prefill-btn"
            onClick={() => addNames(savedTaste.artists)}
          >
            <Sparkles aria-hidden size={15} />
            Use saved Taste ({savedTaste.artists.length})
          </button>
        )}
      </div>

      <div className="group-picker-combo">
        <div className="group-artist-entry">
          <input
            ref={inputRef}
            id={id}
            type="text"
            role="combobox"
            aria-expanded={showMenu}
            aria-controls={listboxId}
            aria-autocomplete="list"
            aria-activedescendant={
              showMenu && activeIndex >= 0 ? `${listboxId}-opt-${activeIndex}` : undefined
            }
            placeholder={placeholder}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setDropdownOpen(true);
              setActiveIndex(-1);
            }}
            onFocus={() => {
              if (trimmed) setDropdownOpen(true);
            }}
            onBlur={() => {
              setTimeout(() => setDropdownOpen(false), 140);
            }}
            onKeyDown={handleKeyDown}
          />
          <button
            type="button"
            className="group-add-btn"
            onClick={addTyped}
            aria-label="Add Artists"
          >
            <Plus aria-hidden size={18} />
            Add
          </button>
        </div>

        {showMenu && (
          <ul
            id={listboxId}
            role="listbox"
            className="group-suggest-list"
            aria-label="Artist suggestions"
          >
            {suggestLoading && options.length === 0 && (
              <li className="group-suggest-status">Searching Artists…</li>
            )}
            {options.map((option, index) => (
              <li
                key={`${option.name}-${option.manual ? "m" : "s"}`}
                id={`${listboxId}-opt-${index}`}
                role="option"
                aria-selected={index === activeIndex}
                className={
                  index === activeIndex
                    ? "group-suggest-option is-active"
                    : "group-suggest-option"
                }
                onMouseDown={(event) => {
                  event.preventDefault();
                  pickOne(option.name);
                }}
              >
                <span>{option.manual ? `Add "${option.name}"` : option.name}</span>
                <Plus aria-hidden size={15} />
              </li>
            ))}
          </ul>
        )}
      </div>

      {artists.length > 0 && (
        <ul className="group-artist-chips" aria-label="Selected Artists">
          {artists.map((artist) => (
            <li key={artist} className="group-artist-chip">
              <span>{artist}</span>
              <button
                type="button"
                aria-label={`Remove ${artist}`}
                onClick={() => removeArtist(artist)}
              >
                <X aria-hidden size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}

      {artists.length > 0 && (visibleRelated.length > 0 || relatedLoading) && (
        <div className="group-related-block" aria-live="polite">
          <span className="group-quick-label">
            {relatedLoading && visibleRelated.length === 0
              ? "Finding related Artists…"
              : "Related Artists (tap to add):"}
          </span>
          {visibleRelated.length > 0 && (
            <div className="group-quick-picks">
              {visibleRelated.slice(0, 12).map((name) => (
                <button
                  key={name}
                  type="button"
                  className="group-quick-chip group-related-chip"
                  onClick={() => addNames([name])}
                >
                  <Plus aria-hidden size={14} />
                  <span>{name}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {artists.length === 0 && (
        <div className="group-quick-picks">
          <span className="group-quick-label">Quick picks:</span>
          {QUICK_PICK_ARTISTS.map((artist) => (
            <button
              key={artist}
              type="button"
              className="group-quick-chip"
              onClick={() => addNames([artist])}
            >
              {artist}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
