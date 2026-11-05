"use client";

import { type SubmitEvent, useState } from "react";

import { ConcertList } from "@/components/concert-list";
import { useSearch } from "@/lib/use-search";

export function Search() {
  const [text, setText] = useState("");
  const { phase, city, status, recommendations, error, search } = useSearch();

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = text.trim();
    if (trimmed) search(trimmed);
  }

  return (
    <>
      <form onSubmit={submit} className="flex gap-2">
        <label htmlFor="city" className="sr-only">
          City
        </label>
        <input
          id="city"
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="Chicago"
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
        {status && <p>{status}</p>}
        {phase === "finished" && !error && recommendations.length === 0 && (
          <p>No Concerts found in {city}. Check the spelling, or try the name of a nearby city.</p>
        )}
      </div>

      {error && (
        <div role="alert" className="mt-6 text-sm">
          <p>{error}</p>
          <button type="button" onClick={() => search(city)} className="mt-1 underline">
            Try again
          </button>
        </div>
      )}

      <ConcertList recommendations={recommendations} />
    </>
  );
}
