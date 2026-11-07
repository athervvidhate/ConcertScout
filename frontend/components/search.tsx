"use client";

import { Button } from "@base-ui/react/button";
import { Turnstile, type TurnstileInstance } from "@marsidev/react-turnstile";
import { LocateFixed } from "lucide-react";
import { type SubmitEvent, useEffect, useRef, useState } from "react";

import { Board, Listings } from "@/components/board";
import { HomeGuide } from "@/components/home-guide";
import { Listing } from "@/components/listing";
import { Poster } from "@/components/poster";
import { SearchFeedback } from "@/components/search-feedback";
import { SiteHeader } from "@/components/site-header";
import { SearchExamples } from "@/components/search-examples";
import { SpotifyShelf } from "@/components/spotify-shelf";
import { useSpotifyConnection } from "@/lib/spotify";
import { countOf, TastePanel } from "@/components/taste-panel";
import { formatInterpreted, formatPosterHeading } from "@/lib/format";
import { forgetPlace, keepPlace, type Place, readPlace } from "@/lib/place";
import { API_URL } from "@/lib/search";
import { useSearchExample } from "@/lib/search-examples";
import { useImportedTaste } from "@/lib/taste";
import { useSearch } from "@/lib/use-search";

const NO_LOCATION = "We could not get your location. Type a city in the search box instead.";
const TURNSTILE_SITE_KEY =
  process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY ?? "1x00000000000000000000AA";

export function Search() {
  const [text, setText] = useState("");
  const [tasteOpen, setTasteOpen] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [botCheckFailed, setBotCheckFailed] = useState(false);
  const botCheck = useRef<TurnstileInstance>(null);
  const taste = useImportedTaste();
  const spotify = useSpotifyConnection();
  const [place, setPlace] = useState<Place | null>(null);
  const [locationError, setLocationError] = useState<string | null>(null);
  const {
    phase,
    run: searchRun,
    searched,
    status,
    interpreted,
    candidates,
    recommendations,
    hasPoster,
    elsewhere,
    error,
    retryable,
    search,
    clear,
  } = useSearch();
  const showPoster = phase === "searching" || hasPoster;
  // Home holds everything that isn't about a Search, so a Search replaces all of it.
  const home = phase === "idle";
  const example = useSearchExample(!text && home);
  const locationLabel = place ? "Forget my location" : "Use my location";
  const canSearch = token !== null && phase !== "searching";
  const searchedFor =
    interpreted && !interpreted.place && place ? { ...interpreted, place: "Near you" } : interpreted;

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
  function shareLocation() {
    setLocationError(null);
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        const here = { lat: coords.latitude, lon: coords.longitude };
        keepPlace(here);
        setPlace(here);
      },
      () => setLocationError(NO_LOCATION),
    );
  }

  function toggleLocation() {
    if (!place) return shareLocation();
    forgetPlace();
    setPlace(null);
  }

  function run(query: string) {
    if (!token) return;
    // Each token works once, so the next Search needs a fresh one.
    setToken(null);
    botCheck.current?.reset();
    // A typed place wins on the server, so a shared location only fills the gap.
    search(query, token, taste?.artists ?? [], place);
  }

  function goHome() {
    setText("");
    clear();
  }

  function tryExample(example: string) {
    setText(example);
    run(example);
  }

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = text.trim();
    if (trimmed) run(trimmed);
  }

  return (
    <>
      <SiteHeader
        onHome={goHome}
        hideBrand={home}
        onTaste={() => setTasteOpen(true)}
        tasteLabel={taste ? `Your Taste: ${countOf(taste.artists)}` : "Your Taste"}
      />
      <TastePanel spotify={spotify} open={tasteOpen} onOpenChange={setTasteOpen} />

      <h1 className={home ? "wordmark" : "sr-only"}>Concert Scout</h1>

      <form onSubmit={submit} className="search-bar">
        <Button
          type="button"
          className="locate"
          data-located={place ? "" : undefined}
          aria-label={locationLabel}
          title={locationLabel}
          onClick={toggleLocation}
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
          placeholder={home ? example : undefined}
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

      {home && <SearchExamples onExample={tryExample} ready={token !== null} />}

      <div aria-live="polite" className="search-context">
        {searchedFor && (
          <p title={formatInterpreted(searchedFor)}>{formatPosterHeading(searchedFor)}</p>
        )}
        {phase === "finished" && !error && recommendations.length === 0 && !elsewhere && (
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

      {showPoster && (
        <Poster
          key={searchRun}
          candidates={candidates}
          recommendations={recommendations}
          searching={phase === "searching"}
          hasPoster={hasPoster}
          status={status}
        />
      )}
      {elsewhere && phase === "finished" && (
        <Board
          title={`Nothing in ${interpreted?.region ?? interpreted?.place?.split(",")[0] ?? "this area"}`}
          subtitle={`These match "${elsewhere.keyword}" in other cities.`}
        >
          <Listings>
            {elsewhere.concerts.map((concert) => (
              <Listing key={concert.id} concert={concert} anywhere />
            ))}
          </Listings>
        </Board>
      )}
      {phase === "finished" && (
        <SearchFeedback
          key={searched}
          search={searched}
          interpreted={interpreted}
          recommendations={recommendations}
          error={error}
        />
      )}
      {spotify.connected && (home || (phase === "finished" && interpreted && !error)) && (
        <SpotifyShelf
          connectHref={spotify.connectHref}
          onLocate={shareLocation}
          upcoming={home}
          key={JSON.stringify([interpreted, place])}
          place={interpreted?.place}
          lat={interpreted?.place ? undefined : place?.lat}
          lon={interpreted?.place ? undefined : place?.lon}
          radius={interpreted?.radius_miles}
          start={interpreted?.start}
          end={interpreted?.end}
          genres={interpreted?.genres}
        />
      )}
      {home && (
        <HomeGuide
          personal={!spotify.connected}
          locationLabel={locationLabel}
          onLocation={toggleLocation}
          onTaste={() => setTasteOpen(true)}
        />
      )}
    </>
  );
}
