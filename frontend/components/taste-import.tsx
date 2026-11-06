"use client";

import { Button } from "@base-ui/react/button";
import { type SubmitEvent, useState } from "react";

import {
  fetchTaste,
  forgetTaste,
  keepTaste,
  SOURCE_NAMES,
  type TasteSource,
  useImportedTaste,
} from "@/lib/taste";

const UNREACHABLE = "Concert Scout's API is not responding.";

export function TasteImport() {
  const taste = useImportedTaste();
  const [source, setSource] = useState<TasteSource>("lastfm");
  const [username, setUsername] = useState("");
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setImporting(true);
    setError(null);
    try {
      keepTaste(await fetchTaste(source, username.trim()));
      setUsername("");
    } catch (caught) {
      setError(caught instanceof TypeError ? UNREACHABLE : (caught as Error).message);
    }
    setImporting(false);
  }

  if (taste) {
    return (
      <section className="taste-import" aria-label="Your imported Taste">
        <p>
          Using {taste.artists.length} Artists from {SOURCE_NAMES[taste.source]}. Name an Artist or
          style in a Search to use that instead.
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
            onChange={(event) => setSource(event.target.value as TasteSource)}
          >
            <option value="lastfm">{SOURCE_NAMES.lastfm}</option>
            <option value="listenbrainz">{SOURCE_NAMES.listenbrainz}</option>
          </select>
        </label>
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
        <Button type="submit" disabled={importing || !username.trim()}>
          {importing ? "Importing" : "Import"}
        </Button>
      </form>
      {error && (
        <p role="alert" className="search-error">
          {error}
        </p>
      )}
    </details>
  );
}
