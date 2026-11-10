"use client";

import { Dialog } from "@base-ui/react/dialog";
import { X } from "lucide-react";
import { useState } from "react";

import { FollowButton } from "@/components/follow-button";
import { type ArtistProfile, spotifyHref, useArtistProfiles } from "@/lib/artist";

const count = new Intl.NumberFormat("en-US");

function Profile({ profile, named }: { profile: ArtistProfile; named: boolean }) {
  const { listeners, bio, tags, top_tracks: tracks, similar } = profile;
  const nothing = listeners === undefined && !bio && !tags.length && !tracks.length && !similar.length;

  return (
    <section className="artist-profile" aria-label={profile.name}>
      {named && <h3 className="artist-part">{profile.name}</h3>}
      <FollowButton name={profile.name} />
      <a
        className="artist-spotify"
        href={spotifyHref(profile)}
        target="_blank"
        rel="noopener noreferrer"
      >
        {profile.spotify_url ? "Open on Spotify" : "Search on Spotify"}
      </a>
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

type Props = { name: string; onOpen?: () => void; className?: string };

/** The Artist's name, which opens what the sources report about them. */
export function ArtistPanel({ name, onOpen, className = "artist-name" }: Props) {
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
      <Dialog.Trigger className={className}>{name}</Dialog.Trigger>
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
