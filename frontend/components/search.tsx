"use client";

import { Button } from "@base-ui/react/button";
import { Turnstile, type TurnstileInstance } from "@marsidev/react-turnstile";
import Link from "next/link";
import { type SubmitEvent, useRef, useState } from "react";

import { NearbyConcerts } from "@/components/nearby";
import { Poster } from "@/components/poster";
import { formatInterpreted, formatPosterHeading } from "@/lib/format";
import { useSearch } from "@/lib/use-search";

const TURNSTILE_SITE_KEY =
  process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY ?? "1x00000000000000000000AA";

export function Search() {
  const [text, setText] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [botCheckFailed, setBotCheckFailed] = useState(false);
  const botCheck = useRef<TurnstileInstance>(null);
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
  const canSearch = token !== null && phase !== "searching";

  function run(query: string) {
    if (!token) return;
    // Each token works once, so the next Search needs a fresh one.
    setToken(null);
    botCheck.current?.reset();
    search(query, token);
  }

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = text.trim();
    if (trimmed) run(trimmed);
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
        <Button type="submit" disabled={!canSearch}>
          Find concerts
        </Button>
      </form>

      <Turnstile
        ref={botCheck}
        siteKey={TURNSTILE_SITE_KEY}
        className="bot-check"
        options={{ appearance: "interaction-only" }}
        onSuccess={(fresh) => {
          setToken(fresh);
          setBotCheckFailed(false);
        }}
        onExpire={() => setToken(null)}
        onError={() => {
          setToken(null);
          setBotCheckFailed(true);
        }}
      />
      {botCheckFailed && (
        <p role="alert" className="search-error">
          The bot check did not load. Reload the page to Search.
        </p>
      )}

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
            <Button type="button" disabled={!canSearch} onClick={() => run(searched)}>
              Try again
            </Button>
          )}
        </div>
      )}

      {phase === "searching" || hasPoster ? (
        <Poster
          candidates={candidates}
          recommendations={recommendations}
          searching={phase === "searching"}
          hasPoster={hasPoster}
          status={status}
        />
      ) : (
        <NearbyConcerts />
      )}
    </>
  );
}
