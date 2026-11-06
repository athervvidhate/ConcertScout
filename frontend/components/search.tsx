"use client";

import { Button } from "@base-ui/react/button";
import Link from "next/link";
import { type SubmitEvent, useState } from "react";

import { Poster } from "@/components/poster";
import { formatInterpreted, formatPosterHeading } from "@/lib/format";
import { useSearch } from "@/lib/use-search";

export function Search() {
  const [text, setText] = useState("");
  const {
    phase,
    searched,
    status,
    interpreted,
    candidates,
    recommendations,
    hasPoster,
    error,
    retryable,
    search,
  } = useSearch();

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = text.trim();
    if (trimmed) search(trimmed);
  }

  return (
    <>
      <form onSubmit={submit} className="search-bar">
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
        />
        <Button type="submit" disabled={phase === "searching"}>
          Find concerts
        </Button>
      </form>

      <nav className="search-nav">
        <Link href="/saved">Saved Concerts</Link>
      </nav>

      <div aria-live="polite" className="search-context">
        {interpreted && (
          <p title={formatInterpreted(interpreted)}>{formatPosterHeading(interpreted)}</p>
        )}
        {phase === "finished" && !error && recommendations.length === 0 && (
          <p>Nothing qualifies for this Search. Try wider dates or a nearby city.</p>
        )}
      </div>

      {error && (
        <div role="alert" className="search-error">
          <p>{error}</p>
          {retryable && (
            <Button type="button" onClick={() => search(searched)}>
              Try again
            </Button>
          )}
        </div>
      )}

      <Poster
        candidates={candidates}
        recommendations={recommendations}
        searching={phase === "searching"}
        hasPoster={hasPoster}
        status={status}
      />
    </>
  );
}
