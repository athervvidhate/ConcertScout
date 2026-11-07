"use client";

import { Button } from "@base-ui/react/button";
import { X } from "lucide-react";
import { useSyncExternalStore } from "react";

import { Ticket } from "@/components/ticket";
import { removeSaved, upcoming, useSavedConcerts } from "@/lib/saved";

const noSubscription = () => () => {};
const MINUTE = 60_000;
const thisMinute = () => Math.floor(Date.now() / MINUTE);

export function SavedConcerts() {
  const saved = useSavedConcerts();
  const minute = useSyncExternalStore(noSubscription, thisMinute, () => 0);
  const concerts = upcoming(saved, new Date(minute * MINUTE));

  if (concerts.length === 0) {
    return <p className="saved-empty">Nothing saved yet. Save a Concert from a Poster.</p>;
  }
  return (
    <ul className="saved-list">
      {concerts.map((recommendation, rank) => (
        <li key={recommendation.concert.id}>
          <Ticket recommendation={recommendation} rank={rank} />
          <Button
            type="button"
            className="saved-remove"
            onClick={() => removeSaved(recommendation.concert.id)}
          >
            <X aria-hidden size={22} />
            <span>Remove</span>
          </Button>
        </li>
      ))}
    </ul>
  );
}
