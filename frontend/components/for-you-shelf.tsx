"use client";

import { Button } from "@base-ui/react/button";
import { useEffect, useState } from "react";

import { Board, Listings } from "@/components/board";
import { Listing } from "@/components/listing";
import {
  type ForYou,
  fetchForYou,
  NEEDS_PLACE,
  noteFor,
  shelfTitle,
} from "@/lib/for-you";
import type { Place } from "@/lib/place";
import { SearchRefused } from "@/lib/search";
import type { ImportedTaste } from "@/lib/taste";

type Props = {
  taste: ImportedTaste;
  place: Place | null;
  signedIn: boolean;
  onLocate: () => void;
};

type State =
  | { status: "loading" }
  | { status: "needs-place" }
  | { status: "failed"; message: string }
  | { status: "ready"; shelf: ForYou };

/** Concerts in the next 60 days that suit the visitor's Taste. Names and bills only, no model. */
export function ForYouShelf({ taste, place, signedIn, onLocate }: Props) {
  const [state, setState] = useState<State>({ status: "loading" });
  // A guest has nowhere to look until the visitor shares a place. An Account may have an Alert place.
  const needsPlace = !signedIn && !place;
  const lat = place?.lat;
  const lon = place?.lon;

  useEffect(() => {
    if (needsPlace) return;
    const controller = new AbortController();
    const here = lat !== undefined && lon !== undefined ? { lat, lon } : null;
    fetchForYou(taste, here, signedIn, controller.signal)
      .then((shelf) => setState({ status: "ready", shelf }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof SearchRefused && error.code === NEEDS_PLACE) {
          setState({ status: "needs-place" });
        } else {
          const message =
            error instanceof Error
              ? error.message
              : "Your For You shelf could not load.";
          setState({ status: "failed", message });
        }
      });
    return () => controller.abort();
  }, [taste, lat, lon, signedIn, needsPlace]);

  const where = state.status === "ready" ? state.shelf.place : "Near you";
  return (
    <Board
      title={shelfTitle(where)}
      subtitle="From your Taste in the next two months"
    >
      {needsPlace || state.status === "needs-place" ? (
        <div className="board-prompt">
          <p>
            Share your location to see Concerts that suit your Taste near you.
          </p>
          <Button type="button" onClick={onLocate}>
            Use my location
          </Button>
        </div>
      ) : state.status === "loading" ? (
        <p role="status">Looking for Concerts that suit your Taste</p>
      ) : state.status === "failed" ? (
        <p role="alert">{state.message}</p>
      ) : state.shelf.concerts.length === 0 ? (
        <p>Nothing from your Taste is playing nearby in the next two months.</p>
      ) : (
        <Listings>
          {state.shelf.concerts.map((item) => (
            <Listing
              key={item.concert.id}
              concert={item.concert}
              artist={item.artist}
              note={noteFor(item)}
            />
          ))}
        </Listings>
      )}
    </Board>
  );
}
