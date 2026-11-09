"use client";

import { Play, Square } from "lucide-react";
import { useState } from "react";

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

  return (
    <div className="listen">
      <button type="button" className="listen-button" onClick={() => setListening(!listening)}>
        {listening ? <Square aria-hidden size={14} /> : <Play aria-hidden size={14} />}
        {listening ? "Stop" : "Listen"}
        <span className="sr-only">
          {listening ? " listening to " : " to "}
          {name}
        </span>
      </button>
      {listening && !profile && <p role="status">Finding {name} on Spotify</p>}
      {listening && profile && !src && (
        <p>
          Spotify has no exact page for {name}.{" "}
          <a href={spotifyHref(profile)} target="_blank" rel="noopener noreferrer">
            Search on Spotify
          </a>
        </p>
      )}
      {listening && src && (
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
      )}
    </div>
  );
}
