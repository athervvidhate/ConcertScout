"use client";

import { Button } from "@base-ui/react/button";
import { Turnstile, type TurnstileInstance } from "@marsidev/react-turnstile";
import { LocateFixed } from "lucide-react";
import Link from "next/link";
import { type SubmitEvent, useEffect, useRef, useState } from "react";

import { NearbyConcerts } from "@/components/nearby";
import { Poster } from "@/components/poster";
import { SpotifyShelf } from "@/components/spotify-shelf";
import { useSpotifyConnection } from "@/lib/spotify";
import { TastePanel } from "@/components/taste-panel";
import { formatInterpreted, formatPosterHeading } from "@/lib/format";
import { forgetPlace, keepPlace, type Place, readPlace } from "@/lib/nearby";
import { API_URL } from "@/lib/search";
import { useSearchExample } from "@/lib/search-examples";
import { useImportedTaste } from "@/lib/taste";
import { useSearch } from "@/lib/use-search";

const NO_LOCATION = "We could not get your location. Type a city in the search box instead.";
const TURNSTILE_SITE_KEY =
  process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY ?? "1x00000000000000000000AA";

export function Search() {
  const [text, setText] = useState("");
  const [focused, setFocused] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [botCheckFailed, setBotCheckFailed] = useState(false);
  const botCheck = useRef<TurnstileInstance>(null);
  const taste = useImportedTaste();
  const spotify = useSpotifyConnection();
  const [place, setPlace] = useState<Place | null>(null);
  const [locationError, setLocationError] = useState<string | null>(null);
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
    clear,
  } = useSearch();
  const showPoster = phase === "searching" || hasPoster;
  const resting = !showPoster && !place && !interpreted && !error;
  const example = useSearchExample(!focused && !text && phase !== "searching");
  const canSearch = token !== null && phase !== "searching";

  useEffect(() => {
    const timer = setTimeout(() => setPlace(readPlace()), 0);
    // Wake the Python function while the visitor reads/types; never delay the Search box.
    const controller = new AbortController();
    const deadline = setTimeout(() => controller.abort(), 5000);
    void fetch(`${API_URL}/health`, {signal: controller.signal}).catch(() => {});
    return () => {
      clearTimeout(timer);
      clearTimeout(deadline);
      controller.abort();
    };
  }, []);

  // The browser asks the visitor first, and only after this button is pressed.
  function showNearby() {
    setLocationError(null);
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        const here = { lat: coords.latitude, lon: coords.longitude };
        keepPlace(here);
        setPlace(here);
        clear();
      },
      () => setLocationError(NO_LOCATION),
    );
  }

  function hideNearby() {
    forgetPlace();
    setPlace(null);
  }

  function run(query: string) {
    if (!token) return;
    // Each token works once, so the next Search needs a fresh one.
    setToken(null);
    botCheck.current?.reset();
    search(query, token, taste?.artists ?? []);
  }

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = text.trim();
    if (trimmed) run(trimmed);
  }

  return (
    <>
      <nav className="top-bar">
        <Link href="/saved">Saved Concerts</Link>
        <TastePanel spotify={spotify} />
      </nav>

      <h1 className={resting ? "wordmark" : "sr-only"}>Concert Scout</h1>

      <form onSubmit={submit} className="search-bar">
        <Button
          type="button"
          className="locate"
          aria-label="Show Concerts near me"
          title="Show Concerts near me"
          onClick={showNearby}
        >
          <LocateFixed aria-hidden size={26} />
        </Button>
        <label htmlFor="search" className="sr-only">
          Search
        </label>
        <input
          id="search"
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder={example}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
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

      {locationError && (
        <p role="alert" className="search-error">
          {locationError}
        </p>
      )}

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

      {showPoster ? (
        <Poster
          candidates={candidates}
          recommendations={recommendations}
          searching={phase === "searching"}
          hasPoster={hasPoster}
          status={status}
        />
      ) : (
        place && <NearbyConcerts place={place} onClose={hideNearby} />
      )}
      {spotify.connected && (
        <SpotifyShelf
          connectHref={spotify.connectHref}
          key={JSON.stringify([interpreted, place])}
          place={interpreted?.place}
          lat={interpreted?.place ? undefined : place?.lat}
          lon={interpreted?.place ? undefined : place?.lon}
          start={interpreted?.start}
          end={interpreted?.end}
        />
      )}
    </>
  );
}
