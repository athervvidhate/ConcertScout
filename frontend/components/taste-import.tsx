"use client";

import { Button } from "@base-ui/react/button";
import { type SubmitEvent, useState } from "react";

import { SearchRefused } from "@/lib/search";
import {
  fetchTaste,
  forgetTaste,
  keepTaste,
  SOURCE_NAMES,
  type TasteSource,
  useImportedTaste,
} from "@/lib/taste";
import { artistsFromHistory, artistsFromList, TasteFileError } from "@/lib/taste-files";

const UNREACHABLE = "Concert Scout's API is not responding.";
const UNREADABLE = "That could not be read. Try again.";
const SOURCE_LABELS: Record<TasteSource, string> = {
  lastfm: "Last.fm",
  listenbrainz: "ListenBrainz",
  history: "Spotify history file",
  list: "Pasted list",
};

function explain(caught: unknown): string {
  if (caught instanceof TypeError) return UNREACHABLE;
  if (caught instanceof SearchRefused || caught instanceof TasteFileError) return caught.message;
  return UNREADABLE;
}

export function TasteImport() {
  const taste = useImportedTaste();
  const [source, setSource] = useState<TasteSource>("lastfm");
  const [username, setUsername] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [list, setList] = useState("");
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ready =
    source === "history" ? files.length > 0 : (source === "list" ? list : username).trim() !== "";

  function read(): Promise<string[]> {
    if (source === "history") return artistsFromHistory(files);
    if (source === "list") return Promise.resolve().then(() => artistsFromList(list));
    return fetchTaste(source, username.trim());
  }

  async function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setImporting(true);
    setError(null);
    try {
      keepTaste({ source, artists: await read() });
      setUsername("");
      setFiles([]);
      setList("");
    } catch (caught) {
      setError(explain(caught));
    }
    setImporting(false);
  }

  if (taste) {
    return (
      <section className="taste-import" aria-label="Your imported Taste">
        <p>
          Using {taste.artists.length === 1 ? "1 Artist" : `${taste.artists.length} Artists`} from{" "}
          {SOURCE_NAMES[taste.source]}. Name an Artist or style in a Search to use that instead.
        </p>
        <Button type="button" onClick={forgetTaste}>
          Remove
        </Button>
      </section>
    );
  }

  return (
    <details className="taste-import" open={error !== null || undefined}>
      <summary>Import your Taste</summary>
      <form onSubmit={submit}>
        <label>
          From
          <select
            value={source}
            onChange={(event) => {
              setSource(event.target.value as TasteSource);
              setError(null);
            }}
          >
            {Object.entries(SOURCE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {source === "history" && (
          <label>
            Extended Streaming History
            <input
              type="file"
              accept=".zip,.json"
              multiple
              onChange={(event) => setFiles([...(event.target.files ?? [])])}
            />
          </label>
        )}
        {source === "list" && (
          <label className="taste-list">
            Artists, one per line, or a CSV
            <textarea value={list} onChange={(event) => setList(event.target.value)} rows={5} />
          </label>
        )}
        {(source === "lastfm" || source === "listenbrainz") && (
          <label>
            Username
            <input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="off"
              spellCheck={false}
              required
              maxLength={64}
            />
          </label>
        )}
        <Button type="submit" disabled={importing || !ready}>
          {importing ? "Importing" : "Import"}
        </Button>
      </form>
      {source === "history" && (
        <p className="taste-note">
          Your file stays on this device. Only the top 50 Artist names go with a Search.
        </p>
      )}
      {error && (
        <p role="alert" className="search-error">
          {error}
        </p>
      )}
    </details>
  );
}
