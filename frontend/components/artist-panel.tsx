"use client";

import { Dialog } from "@base-ui/react/dialog";
import { X } from "lucide-react";
import { useState } from "react";

import { type ArtistProfile, previewSrc, spotifyHref, useArtistProfiles } from "@/lib/artist";

const count = new Intl.NumberFormat("en-US");

/** Spotify's own player, shown as Spotify provides it. */
function Preview({ name, src }: { name: string; src: string }) {
  return (
    <iframe
      className="artist-preview"
      title={`${name} on Spotify`}
      src={src}
      width="100%"
      height="352"
      loading="lazy"
      allowFullScreen
      allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"
    />
  );
}

function Profile({ profile, named }: { profile: ArtistProfile; named: boolean }) {
  const { listeners, bio, tags, top_tracks: tracks, similar } = profile;
  const preview = previewSrc(profile);
  // Nothing from Spotify loads, and no Spotify cookie is set, until Listen is pressed.
  // Focus stays on the button: Escape pressed inside Spotify's iframe would not close the panel.
  const [listening, setListening] = useState(false);
  const nothing = listeners === undefined && !bio && !tags.length && !tracks.length && !similar.length;

  return (
    <section className="artist-profile" aria-label={profile.name}>
      {named && <h3 className="artist-part">{profile.name}</h3>}
      <div className="artist-actions">
        {preview && (
          <button type="button" className="artist-listen" onClick={() => setListening(!listening)}>
            {listening ? "Stop" : "Listen"}
            <span className="sr-only">{listening ? " listening to " : " to "}{profile.name}</span>
          </button>
        )}
        <a
          className="artist-spotify"
          href={spotifyHref(profile)}
          target="_blank"
          rel="noopener noreferrer"
        >
          {profile.spotify_url ? "Open on Spotify" : "Search on Spotify"}
        </a>
      </div>
      {preview && listening && <Preview name={profile.name} src={preview} />}
      {nothing && <p className="artist-missing">We couldn&apos;t find details for {profile.name} on Last.fm.</p>}
      {profile.listeners !== undefined && (
        <p className="artist-listeners">
          {count.format(profile.listeners)} Last.fm listeners
        </p>
      )}
      {profile.tags.length > 0 && (
        <ul className="artist-tags" aria-label="Styles">
          {profile.tags.map((tag) => (
            <li key={tag}>{tag}</li>
          ))}
        </ul>
      )}
      {profile.bio && <p>{profile.bio}</p>}
      {profile.top_tracks.length > 0 && (
        <section>
          <h3>Top songs</h3>
          <ol>
            {profile.top_tracks.map((track) => (
              <li key={track.url}>
                <a href={track.url} target="_blank" rel="noopener noreferrer">
                  {track.name}
                </a>
              </li>
            ))}
          </ol>
        </section>
      )}
      {profile.similar.length > 0 && (
        <section>
          <h3>Similar Artists</h3>
          <p>{profile.similar.join(", ")}</p>
        </section>
      )}
      {profile.lastfm_url && (
        <p className="artist-credit">
          Details from{" "}
          <a href={profile.lastfm_url} target="_blank" rel="noopener noreferrer">
            Last.fm
          </a>
        </p>
      )}
    </section>
  );
}

type Props = { name: string; onOpen?: () => void };

/** The Artist's name, which opens what the sources report about them. */
export function ArtistPanel({ name, onOpen }: Props) {
  const [open, setOpen] = useState(false);
  const profiles = useArtistProfiles(name, open);

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) onOpen?.();
      }}
    >
      <Dialog.Trigger className="artist-name">{name}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Backdrop className="taste-backdrop" />
        <Dialog.Popup className="taste-panel artist-panel">
          <header>
            <Dialog.Title>{name}</Dialog.Title>
            <Dialog.Close className="taste-close" aria-label="Close">
              <X aria-hidden size={24} />
            </Dialog.Close>
          </header>
          {!profiles && <p role="status">Looking up {name}</p>}
          {profiles?.map((profile) => (
            <Profile key={profile.name} profile={profile} named={profiles.length > 1} />
          ))}
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
