"use client";

import { Button } from "@base-ui/react/button";
import { Collapsible } from "@base-ui/react/collapsible";
import { Dialog } from "@base-ui/react/dialog";
import { Popover } from "@base-ui/react/popover";
import { ChevronDown, Info, X } from "lucide-react";
import { type SubmitEvent, useState } from "react";

import { SpotifyControl } from "@/components/spotify-shelf";
import type { SpotifyConnection } from "@/lib/spotify";
import { SearchRefused } from "@/lib/search";
import {
  fetchTaste,
  forgetTaste,
  keepTaste,
  SOURCE_NAMES,
  type TasteSource,
  useImportedTaste,
} from "@/lib/taste";
import { artistsFromHistory, artistsFromList, TasteFileError } from "@/lib/taste-files";

const UNREACHABLE = "Concert Scout's API is not responding.";
const UNREADABLE = "That could not be read. Try again.";
const SPOTIFY_PRIVACY = "https://www.spotify.com/account/privacy/";
const SOURCE_LABELS: Record<TasteSource, string> = {
  lastfm: "Last.fm",
  listenbrainz: "ListenBrainz",
  history: "Spotify history file",
  list: "Pasted list",
};

function explain(caught: unknown): string {
  if (caught instanceof TypeError) return UNREACHABLE;
  if (caught instanceof SearchRefused || caught instanceof TasteFileError) return caught.message;
  return UNREADABLE;
}

export function countOf(artists: string[]): string {
  return artists.length === 1 ? "1 Artist" : `${artists.length} Artists`;
}

function HistoryHelp() {
  return (
    <Popover.Root>
      <Popover.Trigger className="taste-help" aria-label="How to get your Spotify history file">
        <Info aria-hidden size={20} />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner className="taste-help-position" sideOffset={8} collisionPadding={12}>
          <Popover.Popup className="taste-help-popup">
            <Popover.Title render={<h3 />}>Get your Spotify history file</Popover.Title>
            <ol>
              <li>
                Open{" "}
                <a href={SPOTIFY_PRIVACY} target="_blank" rel="noopener noreferrer">
                  Spotify&apos;s privacy page
                </a>{" "}
                and sign in.
              </li>
              <li>Under Download your data, choose Extended streaming history and request it.</li>
              <li>Confirm through the link Spotify emails you.</li>
              <li>When the zip arrives, upload it here. It can take up to 30 days.</li>
            </ol>
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  );
}

function ImportForm() {
  const [source, setSource] = useState<TasteSource>("lastfm");
  const [username, setUsername] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [list, setList] = useState("");
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ready =
    source === "history" ? files.length > 0 : (source === "list" ? list : username).trim() !== "";

  function read(): Promise<string[]> {
    if (source === "history") return artistsFromHistory(files);
    if (source === "list") return Promise.resolve().then(() => artistsFromList(list));
    return fetchTaste(source, username.trim());
  }

  async function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setImporting(true);
    setError(null);
    try {
      keepTaste({ source, artists: await read() });
    } catch (caught) {
      setError(explain(caught));
    }
    setImporting(false);
  }

  return (
    <form onSubmit={submit}>
      <label>
        Import from
        <select
          value={source}
          onChange={(event) => {
            setSource(event.target.value as TasteSource);
            setError(null);
          }}
        >
          {Object.entries(SOURCE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      {source === "history" && (
        <div className="taste-file">
          <label>
            Spotify history file
            <input
              type="file"
              accept=".zip,.json"
              multiple
              onChange={(event) => setFiles([...(event.target.files ?? [])])}
            />
          </label>
          <HistoryHelp />
          <p>Your file stays on this device. Only your top 50 Artist names go with a Search.</p>
        </div>
      )}
      {source === "list" && (
        <label>
          Artists, one per line, or a CSV
          <textarea value={list} onChange={(event) => setList(event.target.value)} rows={7} />
        </label>
      )}
      {(source === "lastfm" || source === "listenbrainz") && (
        <label>
          {SOURCE_LABELS[source]} username
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="off"
            spellCheck={false}
            required
            maxLength={64}
          />
        </label>
      )}
      <Button type="submit" disabled={importing || !ready}>
        {importing ? "Importing" : "Import"}
      </Button>
      {error && <p role="alert">{error}</p>}
    </form>
  );
}

type TastePanelProps = {
  spotify: SpotifyConnection;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function TastePanel({spotify, open, onOpenChange}: TastePanelProps) {
  const taste = useImportedTaste();

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className="taste-backdrop" />
        <Dialog.Popup className="taste-panel">
          <header>
            <Dialog.Title>Your Taste</Dialog.Title>
            <Dialog.Close className="taste-close" aria-label="Close">
              <X aria-hidden size={24} />
            </Dialog.Close>
          </header>
          <SpotifyControl connection={spotify} />
          {taste ? (
            <div className="taste-current">
              <p>
                Using {countOf(taste.artists)} from {SOURCE_NAMES[taste.source]}.
              </p>
              <Button type="button" onClick={forgetTaste}>
                Remove
              </Button>
            </div>
          ) : (
            <Collapsible.Root className="taste-other">
              <Collapsible.Trigger className="taste-other-trigger">
                Other ways to add your Taste
                <ChevronDown aria-hidden size={20} />
              </Collapsible.Trigger>
              <Collapsible.Panel className="taste-other-panel">
                <p>Searches that don&apos;t name an Artist or style use this list. It stays on this device.</p>
                <ImportForm />
              </Collapsible.Panel>
            </Collapsible.Root>
          )}
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
