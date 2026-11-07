"use client";

import { Button } from "@base-ui/react/button";
import { useSyncExternalStore } from "react";

import { Ticket } from "@/components/ticket";
import { localToday } from "@/lib/format";
import { removeSaved, upcoming, useSavedConcerts } from "@/lib/saved";

const noSubscription = () => () => {};

export function SavedConcerts() {
  const saved = useSavedConcerts();
  const today = useSyncExternalStore(noSubscription, localToday, () => "");
  const concerts = upcoming(saved, today);

  if (concerts.length === 0) {
    return <p className="saved-empty">Nothing saved yet. Save a Concert from a Poster.</p>;
  }
  return (
    <ul className="saved-list">
      {concerts.map((recommendation, rank) => (
        <li key={recommendation.concert.id}>
          <Ticket recommendation={recommendation} rank={rank} />
          <Button type="button" onClick={() => removeSaved(recommendation.concert.id)}>
            Remove
          </Button>
        </li>
      ))}
    </ul>
  );
}
