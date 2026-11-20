"use client";

import { Clapperboard, Square } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

import { clipLabel, embedSrc, useLiveClip } from "@/lib/live-clips";

type WatchLiveProps = { name: string; watching: boolean };

/**
 * Turns the Ticket's photograph into an official live performance and back. Focus stays on the
 * button: Escape pressed inside YouTube's frame would not close the Ticket.
 */
export function WatchLiveButton({
  name,
  watching,
  onWatch,
}: WatchLiveProps & { onWatch: (watching: boolean) => void }) {
  return (
    <button
      type="button"
      className="ticket-pill"
      aria-pressed={watching}
      onClick={() => onWatch(!watching)}
    >
      {watching ? <Square aria-hidden size={14} /> : <Clapperboard aria-hidden size={16} />}
      {watching ? "Stop" : "Watch Live"}
      <span className="sr-only">
        {watching ? " watching " : " performance of "}
        {name}
        {watching && " live"}
      </span>
    </button>
  );
}

/**
 * YouTube's player for the Artist's live clip, in the photograph's box, so nothing around it moves.
 * Nothing loads from YouTube, and no YouTube cookie is set, until Watch Live is pressed. The player
 * starts at its peak moment and waits for a press of play, and nothing of ours covers it.
 */
export function WatchLiveStage({ name, watching }: WatchLiveProps) {
  const reduced = useReducedMotion();
  const lookup = useLiveClip(name, watching);
  const clip = lookup && "clip" in lookup ? lookup.clip : null;
  const src = clip ? embedSrc(clip) : null;

  return (
    <AnimatePresence>
      {watching && (
        <motion.div
          key="stage"
          className="listen-stage watch-stage"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: reduced ? 0 : 0.35, ease: [0.22, 0.8, 0.2, 1] }}
        >
          {!lookup && <p role="status">Finding a live performance by {name}</p>}
          {lookup && "error" in lookup && <p role="alert">{lookup.error}</p>}
          {lookup && "clip" in lookup && !src && (
            <p role="status">No official live performance by {name} to show yet.</p>
          )}
          {clip && src && (
            <>
              <iframe
                className="watch-player"
                title={`${name} live: ${clip.title}`}
                src={src}
                loading="lazy"
                allowFullScreen
                allow="accelerometer; encrypted-media; gyroscope; picture-in-picture; fullscreen"
                referrerPolicy="strict-origin-when-cross-origin"
              />
              <p className="watch-label">{clipLabel(clip)}</p>
            </>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
