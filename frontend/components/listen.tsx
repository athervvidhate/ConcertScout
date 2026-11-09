"use client";

import { Play, Square } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useRef, useState } from "react";

import { previewSrc, spotifyHref, useArtistProfiles } from "@/lib/artist";

/**
 * Spotify's player for a Ticket's headliner. Nothing loads from Spotify, and no Spotify cookie is
 * set, until Listen is pressed. Focus stays on the button: Escape pressed inside Spotify's frame
 * would not close the Ticket.
 */
export function Listen({ name }: { name: string }) {
  const [listening, setListening] = useState(false);
  const profiles = useArtistProfiles(name, listening);
  const profile = profiles?.[0];
  const src = profile ? previewSrc(profile) : null;
  const reduced = useReducedMotion();
  const body = useRef<HTMLDivElement>(null);

  return (
    <div className="listen">
      <button
        type="button"
        className="listen-button"
        aria-busy={listening && !profile}
        onClick={() => setListening(!listening)}
      >
        {listening ? <Square aria-hidden size={14} /> : <Play aria-hidden size={14} />}
        {listening ? "Stop" : "Listen"}
        <span className="sr-only">
          {listening ? " listening to " : " to "}
          {name}
        </span>
      </button>
      {listening && !profile && (
        <p className="sr-only" role="status">
          Finding {name} on Spotify
        </p>
      )}
      {/* It opens once the lookup answers, so it slides to its full height in one movement. */}
      <AnimatePresence initial={false}>
        {listening && profile && (
          <motion.div
            key="body"
            ref={body}
            className="listen-body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: reduced ? 0 : 0.45, ease: [0.22, 0.8, 0.2, 1] }}
            // The Ticket keeps its size, so a player that opens below the fold scrolls into view.
            onAnimationComplete={() => {
              if (listening) {
                body.current?.scrollIntoView({
                  block: "nearest",
                  behavior: reduced ? "auto" : "smooth",
                });
              }
            }}
          >
            {src ? (
              <iframe
                className="listen-player"
                title={`${name} on Spotify`}
                src={src}
                width="100%"
                height="352"
                loading="lazy"
                allowFullScreen
                allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"
              />
            ) : (
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
    </div>
  );
}
