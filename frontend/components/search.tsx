"use client";

import { type SubmitEvent, useState } from "react";

import { ConcertList } from "@/components/concert-list";
import { formatInterpreted } from "@/lib/format";
import { useSearch } from "@/lib/use-search";

export function Search() {
  const [text, setText] = useState("");
  const { phase, searched, status, interpreted, total, recommendations, error, retryable, search } =
    useSearch();

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = text.trim();
    if (trimmed) search(trimmed);
  }

  return (
    <>
      <form onSubmit={submit} className="flex gap-2">
        <label htmlFor="search" className="sr-only">
          Search
        </label>
        <input
          id="search"
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="Something like Khruangbin in Chicago, next two weekends"
          required
          maxLength={500}
          className="min-w-0 flex-1 rounded border border-stone-300 bg-white px-3 py-2"
        />
        <button
          type="submit"
          disabled={phase === "searching"}
          className="rounded bg-stone-900 px-4 py-2 text-white disabled:opacity-50"
        >
          Search
        </button>
      </form>

      <div aria-live="polite" className="mt-6 text-sm text-stone-600">
        {interpreted && <p>{formatInterpreted(interpreted)}</p>}
        {status && <p>{status}</p>}
        {total !== null && total > recommendations.length && recommendations.length > 0 && (
          <p>
            Showing {recommendations.length} of {total.toLocaleString("en-US")} Concerts
          </p>
        )}
        {phase === "finished" && !error && recommendations.length === 0 && (
          <p>No Concerts found for this Search. Try wider dates or a nearby city.</p>
        )}
      </div>

      {error && (
        <div role="alert" className="mt-6 text-sm">
          <p>{error}</p>
          {retryable && (
            <button type="button" onClick={() => search(searched)} className="mt-1 underline">
              Try again
            </button>
          )}
        </div>
      )}

      <ConcertList recommendations={recommendations} />
    </>
  );
}
