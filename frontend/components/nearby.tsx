"use client";

import { Autocomplete } from "@base-ui/react/autocomplete";
import { Button } from "@base-ui/react/button";
import { useEffect, useState } from "react";

import { formatDate, formatTime } from "@/lib/format";
import { findPlaces, keepPlace, type Place, readPlace, useNearby } from "@/lib/nearby";
import type { Concert } from "@/lib/search";

const TYPING_PAUSE_MS = 250;
const NO_LOCATION = "We could not get your location. Choose a place instead.";

function usePlaceOptions(text: string): Place[] {
  const [options, setOptions] = useState<Place[]>([]);

  useEffect(() => {
    if (text.trim().length < 2) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      findPlaces(text, controller.signal).then(setOptions, () => setOptions([]));
    }, TYPING_PAUSE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [text]);

  return options;
}

function NearbyConcert({ concert }: { concert: Concert }) {
  const when = [
    concert.date && formatDate(concert.date),
    concert.time && formatTime(concert.time),
  ].filter(Boolean);
  return (
    <li>
      <a href={concert.url}>{concert.artists[0]?.name ?? concert.name}</a>
      <span>{[when.join(" at "), concert.venue].filter(Boolean).join(" · ")}</span>
    </li>
  );
}

export function NearbyConcerts() {
  const [place, setPlace] = useState<Place | null>(null);
  const [text, setText] = useState("");
  const [locationError, setLocationError] = useState<string | null>(null);
  const options = usePlaceOptions(text);
  const nearby = useNearby(place);

  useEffect(() => {
    const timer = setTimeout(() => {
      const kept = readPlace();
      if (!kept) return;
      setPlace(kept);
      setText(kept.name);
    }, 0);
    return () => clearTimeout(timer);
  }, []);

  function choose(chosen: Place) {
    keepPlace(chosen);
    setPlace(chosen);
    setText(chosen.name);
    setLocationError(null);
  }

  // The browser asks the visitor first, and only after this button is pressed.
  function useLocation() {
    navigator.geolocation.getCurrentPosition(
      ({ coords }) =>
        choose({ name: "Your location", lat: coords.latitude, lon: coords.longitude }),
      () => setLocationError(NO_LOCATION),
    );
  }

  return (
    <section className="nearby" aria-label="Concerts near you">
      <div className="nearby-controls">
        <Autocomplete.Root
          items={options}
          value={text}
          onValueChange={setText}
          filter={null}
          itemToStringValue={(option: Place) => option.name}
        >
          <label className="sr-only" htmlFor="nearby-place">
            Show Concerts near a place
          </label>
          <Autocomplete.Input id="nearby-place" placeholder="Show Concerts near a place" />
          <Autocomplete.Portal>
            <Autocomplete.Positioner sideOffset={4}>
              <Autocomplete.Popup className="nearby-options">
                <Autocomplete.List>
                  {(option: Place) => (
                    <Autocomplete.Item
                      key={`${option.lat},${option.lon}`}
                      value={option}
                      onClick={() => choose(option)}
                    >
                      {option.name}
                    </Autocomplete.Item>
                  )}
                </Autocomplete.List>
              </Autocomplete.Popup>
            </Autocomplete.Positioner>
          </Autocomplete.Portal>
        </Autocomplete.Root>
        <Button type="button" onClick={useLocation}>
          Use my location
        </Button>
      </div>
      <div aria-live="polite">
        {locationError && <p>{locationError}</p>}
        {nearby.loading && <p>Looking for Concerts nearby</p>}
        {nearby.error && <p>{nearby.error}</p>}
        {nearby.empty && <p>No Concerts found in the next month. Try a nearby city.</p>}
      </div>
      {nearby.concerts.length > 0 && (
        <ul className="nearby-list">
          {nearby.concerts.map((concert) => (
            <NearbyConcert key={concert.id} concert={concert} />
          ))}
        </ul>
      )}
    </section>
  );
}
