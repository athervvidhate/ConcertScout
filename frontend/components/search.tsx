"use client";

import { Button } from "@base-ui/react/button";
import { Turnstile, type TurnstileInstance } from "@marsidev/react-turnstile";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ArrowRight, LocateFixed } from "lucide-react";
import { type SubmitEvent, useEffect, useRef, useState } from "react";

import { SearchChips } from "@/components/search-chips";
import { SearchInput } from "@/components/search-input";
import { HomeHero } from "@/components/home-hero";
import { HomeStrip } from "@/components/home-strip";
import { useHomeExamples } from "@/lib/home-examples";
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
import { useImportedTaste } from "@/lib/taste";
import { useSearch } from "@/lib/use-search";

const NO_LOCATION =
  "We could not get your location. Type a city in the search box instead.";
const TURNSTILE_SITE_KEY =
  process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY ?? "1x00000000000000000000AA";

export function Search() {
  const examples = useHomeExamples();
  const reduced = useReducedMotion();
  const [activeExample, setActiveExample] = useState(0);
  const [returningHome, setReturningHome] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const [exampleNotice, setExampleNotice] = useState("");
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
    step,
    interpreted,
    candidates,
    recommendations,
    hasPoster,
    elsewhere,
    error,
    retryable,
    search,
    clear,
    showExample,
  } = useSearch();
  const showPoster = phase === "searching" || hasPoster;
  // Home holds everything that isn't about a Search, so a Search replaces all of it.
  const home = phase === "idle";
  const locationLabel = place ? "Forget my location" : "Use my location";
  const canSearch = token !== null && phase !== "searching";
  const searchedFor =
    interpreted && !interpreted.place && place
      ? { ...interpreted, place: "Near you" }
      : interpreted;

  useEffect(() => {
    const timer = setTimeout(() => setPlace(readPlace()), 0);
    // Wake the Python function while the visitor reads/types; never delay the Search box.
    const controller = new AbortController();
    const deadline = setTimeout(() => controller.abort(), 5000);
    void fetch(`${API_URL}/health`, { signal: controller.signal }).catch(
      () => {},
    );
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

  function run(query: string, near: Place | null = place) {
    if (!token) return;
    // Each token works once, so the next Search needs a fresh one.
    setToken(null);
    botCheck.current?.reset();
    // A typed place wins on the server, so a shared location only fills the gap.
    search(query, token, taste?.artists ?? [], near);
    input.current?.blur();
    window.scrollTo({ top: 0, behavior: reduced ? "instant" : "smooth" });
  }

  function goHome() {
    setReturningHome(true);
    window.scrollTo({ top: 0, behavior: "instant" });
    setActiveExample(0);
    setText("");
    setExampleNotice("");
    clear();
  }

  function tryExample(example: string) {
    setText(example);
    const cached = examples.find((item) => item.text === example);
    if (cached) {
      showExample(cached);
      input.current?.blur();
      window.scrollTo({ top: 0, behavior: reduced ? "instant" : "smooth" });
      setExampleNotice("");
    } else
      setExampleNotice(
        "This example is being refreshed. You can Search with these words instead.",
      );
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
        onTaste={() => setTasteOpen(true)}
        tasteLabel={
          taste ? `Your Taste: ${countOf(taste.artists)}` : "Your Taste"
        }
      />
      <TastePanel
        spotify={spotify}
        open={tasteOpen}
        onOpenChange={setTasteOpen}
      />

      <AnimatePresence>
        {home && (
          <HomeHero
            key="hero"
            onCycle={setActiveExample}
            returning={returningHome}
          />
        )}
      </AnimatePresence>
      {!home && <h1 className="sr-only">Concert Scout</h1>}

      <motion.form
        layout="position"
        initial={{ opacity: reduced ? 1 : 0, y: reduced ? 0 : 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{
          layout: { duration: reduced ? 0 : 0.8, ease: [0.87, 0, 0.13, 1] },
          opacity: { duration: reduced ? 0 : 1, delay: reduced ? 0 : 0.25 },
          y: {
            duration: reduced ? 0 : 1,
            delay: reduced ? 0 : 0.25,
            ease: [0.16, 1, 0.3, 1],
          },
        }}
        onSubmit={submit}
        className={`search-bar ${text.trim() ? "ready" : ""} ${home ? "" : "compact"}`}
      >
        <label htmlFor="search" className="sr-only">
          Search
        </label>
        <SearchInput
          text={text}
          onText={setText}
          home={home}
          inputRef={input}
        />
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
        <Button
          type="submit"
          className="search-send"
          aria-label="Search"
          disabled={!canSearch}
        >
          <span className="send-label">Search</span>
          <ArrowRight aria-hidden size={22} />
        </Button>
      </motion.form>

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

      <AnimatePresence>
        {home && (
          <motion.div
            key="home-intro"
            initial={
              returningHome ? { opacity: 0, y: reduced ? 0 : 20 } : false
            }
            animate={{ opacity: 1, y: 0 }}
            exit={{
              opacity: 0,
              y: reduced ? 0 : -14,
              transition: { duration: reduced ? 0 : 0.28 },
            }}
            transition={{
              duration: reduced ? 0 : 0.8,
              delay: reduced ? 0 : 0.38,
              ease: [0.16, 1, 0.3, 1],
            }}
          >
            <motion.p
              className="pitch"
              initial={
                returningHome
                  ? false
                  : { opacity: reduced ? 1 : 0, y: reduced ? 0 : 24 }
              }
              animate={{ opacity: 1, y: 0 }}
              transition={{
                duration: reduced ? 0 : 1,
                delay: reduced ? 0 : 0.33,
                ease: [0.16, 1, 0.3, 1],
              }}
            >
              An Artist, a sound, a place. We find the Concerts worth going out
              for.
            </motion.p>
            <SearchExamples onExample={tryExample} ready />
            {exampleNotice && <p role="status">{exampleNotice}</p>}
            {!spotify.connected && (
              <HomeStrip
                active={activeExample}
                entering={!returningHome}
                examples={examples}
                onExample={tryExample}
              />
            )}
          </motion.div>
        )}
      </AnimatePresence>

      <div aria-live="polite" className="search-context">
        {searchedFor && (
          <>
            <p title={formatInterpreted(searchedFor)}>
              {formatPosterHeading(searchedFor)}
            </p>
            <motion.div
              key={JSON.stringify(searchedFor)}
              className="understood"
              aria-label="How we read your Search"
              initial="hidden"
              animate="shown"
              variants={{
                hidden: {},
                shown: { transition: { staggerChildren: reduced ? 0 : 0.08 } },
              }}
            >
              <SearchChips interpreted={searchedFor} />
            </motion.div>
          </>
        )}
      </div>

      {error && (
        <div role="alert" className="search-error">
          <p>{error}</p>
          {retryable && (
            <Button
              type="button"
              disabled={!canSearch}
              onClick={() => run(searched)}
            >
              Try again
            </Button>
          )}
        </div>
      )}

      <AnimatePresence mode="popLayout" initial={false}>
        {showPoster && (
          <motion.div
            key={searchRun}
            exit={{ opacity: 0, y: reduced ? 0 : -8 }}
            transition={{ duration: reduced ? 0 : 0.25 }}
          >
            <Poster
              key={searchRun}
              candidates={candidates}
              recommendations={recommendations}
              searching={phase === "searching"}
              hasPoster={hasPoster}
              status={status}
              step={step}
              onChange={() => {
                input.current?.focus();
                input.current?.select();
              }}
              onWiderDates={
                canSearch && searchedFor
                  ? () => {
                      const words = [
                        ...searchedFor.artists,
                        ...searchedFor.genres,
                        searchedFor.region ?? searchedFor.place,
                      ]
                        .filter(Boolean)
                        .join(" ");
                      const wider = `${words} in the next three months`;
                      setText(wider);
                      run(wider);
                    }
                  : undefined
              }
              onAnywhere={
                elsewhere
                  ? () =>
                      document.getElementById("elsewhere")?.scrollIntoView({
                        behavior: reduced ? "instant" : "smooth",
                      })
                  : canSearch && interpreted && interpreted.artists.length > 0
                    ? () => {
                        const anywhere = [
                          ...interpreted.artists,
                          ...interpreted.genres,
                        ].join(" ");
                        setText(anywhere);
                        run(anywhere, null);
                      }
                    : undefined
              }
            />
          </motion.div>
        )}
      </AnimatePresence>
      {elsewhere && phase === "finished" && (
        <div id="elsewhere">
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
        </div>
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
      {spotify.connected &&
        (home || (phase === "finished" && interpreted && !error)) && (
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
      <AnimatePresence initial={false}>
        {home && (
          <motion.div
            key="guide"
            initial={{ opacity: 0, y: reduced ? 0 : 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{
              opacity: 0,
              y: reduced ? 0 : -14,
              transition: { duration: reduced ? 0 : 0.28 },
            }}
            transition={{
              duration: reduced ? 0 : 0.8,
              delay: reduced ? 0 : 0.46,
              ease: [0.16, 1, 0.3, 1],
            }}
          >
            <HomeGuide
              personal={!spotify.connected}
              locationLabel={locationLabel}
              onLocation={toggleLocation}
              onTaste={() => setTasteOpen(true)}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
