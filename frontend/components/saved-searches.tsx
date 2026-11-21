"use client";

import { Bell, Check } from "lucide-react";
import { useState } from "react";

import {
  deleteSavedSearch,
  isSearchSaved,
  MAX_SAVED_SEARCHES,
  saveSearch,
  summarizeReading,
  useSavedSearches,
} from "@/lib/saved-searches";
import { type Reading, SearchRefused } from "@/lib/search";

function failure(caught: unknown, fallback: string): string {
  return caught instanceof SearchRefused ? caught.message : fallback;
}

function formatChecked(iso: string | null | undefined): string {
  if (!iso) return "Reruns weekly";
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return "Reruns weekly";
  return `Last checked ${new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(parsed)}`;
}

/** Poster action for a signed-in Account to keep a Search for weekly Alert reruns. */
export function SaveSearchButton({
  queryText,
  reading,
}: {
  queryText: string;
  reading: Reading;
}) {
  const savedSearches = useSavedSearches();
  const [pending, setPending] = useState(false);
  const [justSaved, setJustSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const alreadySaved =
    justSaved || (savedSearches ? isSearchSaved(savedSearches, queryText, reading) : false);

  async function save() {
    if (pending || alreadySaved) return;
    setError(null);
    setPending(true);
    try {
      await saveSearch(queryText, reading);
      setJustSaved(true);
    } catch (caught) {
      setError(failure(caught, "We could not save this Search. Try again soon."));
    } finally {
      setPending(false);
    }
  }

  return (
    <span className="share">
      <button
        type="button"
        className="save-action share-action"
        data-saved={alreadySaved ? "" : undefined}
        aria-busy={pending}
        disabled={pending || alreadySaved}
        onClick={() => void save()}
      >
        {alreadySaved ? <Check aria-hidden size={19} /> : <Bell aria-hidden size={19} />}
        <span>{alreadySaved ? "Search saved" : "Save this Search"}</span>
      </button>
      <span aria-live="polite" className="sr-only">
        {alreadySaved ? "Saved Search kept for weekly Alerts." : ""}
      </span>
      {error && (
        <span role="alert" className="share-error">
          {error}
        </span>
      )}
    </span>
  );
}

/** The Account page's Saved Searches section: list, cap status, and removal. */
export function SavedSearches() {
  const savedSearches = useSavedSearches();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!savedSearches) return <p role="status">Loading your Saved Searches</p>;

  async function remove(id: string) {
    setBusyId(id);
    setError(null);
    try {
      await deleteSavedSearch(id);
    } catch (caught) {
      setError(failure(caught, "That Saved Search could not be removed. Try again soon."));
    } finally {
      setBusyId(null);
    }
  }

  const atLimit = savedSearches.length >= MAX_SAVED_SEARCHES;

  return (
    <section aria-labelledby="saved-searches-heading">
      <h2 id="saved-searches-heading">Saved Searches</h2>
      <p>
        Concert Scout reruns each Saved Search once a week and folds new Recommendations into your
        daily Alert email. You can keep up to {MAX_SAVED_SEARCHES} Saved Searches.
      </p>
      {savedSearches.length > 0 && (
        <p className="saved-search-count">
          {savedSearches.length} of {MAX_SAVED_SEARCHES} Saved Searches
          {atLimit ? " — remove one to save another." : "."}
        </p>
      )}
      {savedSearches.length === 0 ? (
        <p>You have no Saved Searches yet. Run a Search and choose Save this Search on the Poster.</p>
      ) : (
        <ul className="followed-artists saved-searches-list">
          {savedSearches.map((item) => {
            const summary = summarizeReading(item.reading);
            return (
              <li key={item.id}>
                <div className="saved-search-copy">
                  <strong>{item.query_text}</strong>
                  {summary && <span className="saved-search-meta">{summary}</span>}
                  <span className="saved-search-meta">{formatChecked(item.last_run_at)}</span>
                </div>
                <button
                  type="button"
                  disabled={busyId === item.id}
                  onClick={() => void remove(item.id)}
                >
                  Remove<span className="sr-only"> {item.query_text}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
