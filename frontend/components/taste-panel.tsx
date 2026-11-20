"use client";

import { Button } from "@base-ui/react/button";
import { Collapsible } from "@base-ui/react/collapsible";
import { Dialog } from "@base-ui/react/dialog";
import { Popover } from "@base-ui/react/popover";
import { ChevronDown, Info, X } from "lucide-react";
import { type SubmitEvent, useState } from "react";

import { SpotifyControl } from "@/components/spotify-shelf";
import { PlaylistCsvImport, TasteSeedPicker } from "@/components/taste-seed-picker";
import { YouTubeImport } from "@/components/youtube-import";
import { useAccount } from "@/lib/account";
import type { SpotifyConnection } from "@/lib/spotify";
import { SearchRefused } from "@/lib/search";
import {
  fetchTaste,
  forgetTaste,
  isFileTasteSource,
  keepTaste,
  SOURCE_NAMES,
  type TasteSource,
  useImportedTaste,
} from "@/lib/taste";
import { artistsFromHistory, artistsFromList, TasteFileError } from "@/lib/taste-files";

import pickerStyles from "./taste-seed-picker.module.css";

const UNREACHABLE = "Concert Scout's API is not responding.";
const UNREADABLE = "That could not be read. Try again.";
const SPOTIFY_PRIVACY = "https://www.spotify.com/account/privacy/";

export type ImportOption =
  | "seed"
  | "csv"
  | "youtube"
  | "lastfm"
  | "listenbrainz"
  | "history"
  | "list";

const SOURCE_LABELS: Record<ImportOption, string> = {
  seed: "Pick Artists (30 sec)",
  csv: "Exportify / TuneMyMusic CSV",
  youtube: "YouTube playlist",
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

function formatImportDate(iso?: string): string | null {
  if (!iso) return null;
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function optionForSource(source: TasteSource): ImportOption {
  if (source === "exportify" || source === "tunemymusic" || source === "csv") return "csv";
  return source;
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

type ImportFormProps = {
  source: ImportOption;
  onSourceChange: (source: ImportOption) => void;
  initialArtists?: string[];
  onSaved?: () => void;
  onCancel?: () => void;
};

function ImportForm({
  source,
  onSourceChange,
  initialArtists,
  onSaved,
  onCancel,
}: ImportFormProps) {
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
    if (source === "lastfm" || source === "listenbrainz") {
      return fetchTaste(source, username.trim());
    }
    return Promise.resolve([]);
  }

  async function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setImporting(true);
    setError(null);
    try {
      if (source === "history" || source === "list" || source === "lastfm" || source === "listenbrainz") {
        keepTaste({ source, artists: await read(), importedAt: new Date().toISOString() });
        onSaved?.();
      }
    } catch (caught) {
      setError(explain(caught));
    }
    setImporting(false);
  }

  return (
    <>
      <label>
        Import from
        <select
          value={source}
          onChange={(event) => {
            onSourceChange(event.target.value as ImportOption);
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
      {source === "seed" ? (
        <TasteSeedPicker initialArtists={initialArtists} onSaved={onSaved} onCancel={onCancel} />
      ) : source === "csv" ? (
        <PlaylistCsvImport onSaved={onSaved} onCancel={onCancel} />
      ) : source === "youtube" ? (
        <YouTubeImport onSaved={onSaved} />
      ) : (
        <form onSubmit={submit}>
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
          {onCancel && (
            <Button type="button" className={pickerStyles.secondary} onClick={onCancel}>
              Cancel
            </Button>
          )}
          {error && <p role="alert">{error}</p>}
        </form>
      )}
    </>
  );
}

type TastePanelProps = {
  spotify: SpotifyConnection;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialSource?: ImportOption;
};

function TastePanelBody({
  spotify,
  initialSource,
}: {
  spotify: SpotifyConnection;
  initialSource?: ImportOption;
}) {
  const taste = useImportedTaste();
  // A signed-in Account keeps its Taste on every device it signs in to.
  const kept = useAccount().status === "signed-in" ? "Synced to your account." : "Saved on this device.";
  const [otherOpen, setOtherOpen] = useState(initialSource !== undefined);
  const [source, setSource] = useState<ImportOption>(initialSource ?? "seed");
  const [updating, setUpdating] = useState(false);

  const importedDate = formatImportDate(taste?.importedAt);
  const fileProvenance = taste ? isFileTasteSource(taste.source) : false;

  function openOtherWith(nextSource: ImportOption) {
    setSource(nextSource);
    setOtherOpen(true);
  }

  return (
    <>
      <SpotifyControl connection={spotify} />
      {!taste && !spotify.connected && (
        <div className={pickerStyles.panelHint}>
          <p>
            Not on the invite list? Export a playlist with Exportify or TuneMyMusic and drop the
            CSV here, or pick 3–5 Artists in seconds.
          </p>
          <div className={pickerStyles.panelHintActions}>
            <Button
              type="button"
              className={pickerStyles.panelHintButton}
              onClick={() => openOtherWith("seed")}
            >
              Pick Artists
            </Button>
            <Button
              type="button"
              className={pickerStyles.panelHintButton}
              onClick={() => openOtherWith("csv")}
            >
              Drop CSV file
            </Button>
          </div>
        </div>
      )}
      {taste && !updating ? (
        <div className={pickerStyles.currentCard}>
          <div className="taste-current">
            <p>
              Using {countOf(taste.artists)} from {SOURCE_NAMES[taste.source]}.
            </p>
          </div>
          {fileProvenance ? (
            <p className={pickerStyles.currentMeta}>
              {importedDate ? `Imported ${importedDate} · ` : ""}
              File import on this device (not a live Spotify connection).
            </p>
          ) : (
            importedDate && (
              <p className={pickerStyles.currentMeta}>Saved {importedDate} · {kept}</p>
            )
          )}
          <div className={pickerStyles.currentActions}>
            {fileProvenance && (
              <Button
                type="button"
                className={pickerStyles.currentPrimary}
                onClick={() => {
                  setSource(optionForSource(taste.source));
                  setUpdating(true);
                }}
              >
                Update import
              </Button>
            )}
            {taste.source === "seed" && (
              <Button
                type="button"
                className={pickerStyles.currentPrimary}
                onClick={() => {
                  setSource("seed");
                  setUpdating(true);
                }}
              >
                Edit picks
              </Button>
            )}
            <Button
              type="button"
              className={
                fileProvenance || taste.source === "seed"
                  ? pickerStyles.currentSecondary
                  : pickerStyles.currentPrimary
              }
              onClick={forgetTaste}
            >
              Remove
            </Button>
          </div>
        </div>
      ) : taste && updating ? (
        <div className="taste-other">
          <div className="taste-other-panel">
            <ImportForm
              source={source}
              onSourceChange={setSource}
              initialArtists={taste.source === "seed" ? taste.artists : undefined}
              onSaved={() => setUpdating(false)}
              onCancel={() => setUpdating(false)}
            />
          </div>
        </div>
      ) : (
        <Collapsible.Root
          className="taste-other"
          open={otherOpen}
          onOpenChange={setOtherOpen}
        >
          <Collapsible.Trigger className="taste-other-trigger">
            Other ways to add your Taste
            <ChevronDown aria-hidden size={20} />
          </Collapsible.Trigger>
          <Collapsible.Panel className="taste-other-panel">
            <p>
              Searches that don&apos;t name an Artist or style use this list. It stays on this
              device, and an account syncs it.
            </p>
            <ImportForm source={source} onSourceChange={setSource} />
          </Collapsible.Panel>
        </Collapsible.Root>
      )}
    </>
  );
}

export function TastePanel({ spotify, open, onOpenChange, initialSource }: TastePanelProps) {
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
          {open && (
            <TastePanelBody
              key={initialSource ?? "default"}
              spotify={spotify}
              initialSource={initialSource}
            />
          )}
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
