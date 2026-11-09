"use client";

import { Play, Square } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

import { previewSrc, spotifyHref, useArtistProfiles } from "@/lib/artist";

type ListenProps = { name: string; listening: boolean };

/**
 * Turns the Ticket's photograph into Spotify's player and back. Focus stays on the button: Escape
 * pressed inside Spotify's frame would not close the Ticket.
 */
export function ListenButton({
  name,
  listening,
  onListen,
}: ListenProps & { onListen: (listening: boolean) => void }) {
  return (
    <button
      type="button"
      className="ticket-pill"
      aria-pressed={listening}
      onClick={() => onListen(!listening)}
    >
      {listening ? <Square aria-hidden size={14} /> : <Play aria-hidden size={14} />}
      {listening ? "Stop" : "Listen"}
      <span className="sr-only">
        {listening ? " listening to " : " to "}
        {name}
      </span>
    </button>
  );
}

/**
 * Spotify's player for the headliner, laid over the photograph in the same box, so nothing around
 * it moves. Nothing loads from Spotify, and no Spotify cookie is set, until Listen is pressed.
 */
export function ListenStage({ name, listening }: ListenProps) {
  const reduced = useReducedMotion();
  const profiles = useArtistProfiles(name, listening);
  const profile = profiles?.[0];
  const src = profile ? previewSrc(profile) : null;

  return (
    <AnimatePresence>
      {listening && (
        <motion.div
          key="stage"
          className="listen-stage"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: reduced ? 0 : 0.35, ease: [0.22, 0.8, 0.2, 1] }}
        >
          {!profile && <p role="status">Finding {name} on Spotify</p>}
          {profile && src && (
            <iframe
              className="listen-player"
              title={`${name} on Spotify`}
              src={src}
              width="100%"
              height="100%"
              loading="lazy"
              allowFullScreen
              allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"
            />
          )}
          {profile && !src && (
            <p>
              Spotify has no exact page for {name}.{" "}
              <a href={spotifyHref(profile)} target="_blank" rel="noopener noreferrer">
                Search on Spotify
              </a>
            </p>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
