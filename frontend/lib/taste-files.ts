import { unzip } from "fflate";
import Papa from "papaparse";

const HISTORY_SIZE = 50;
const LIST_SIZE = 100;
// The API refuses a longer Artist name, so one stray line must not sink the whole list.
const LONGEST_NAME = 200;
const HISTORY_FILE = /Streaming_History_Audio[^/]*\.json$/;
const ARTIST_COLUMNS = ["artist", "artists", "artist name", "artistname"];

const NOT_A_HISTORY_FILE =
  "That is not a Spotify Extended Streaming History file. Choose the zip or its Streaming_History_Audio JSON files.";

// A message the visitor can act on, as opposed to an unexpected failure.
export class TasteFileError extends Error {}

type Play = { ms_played?: unknown; master_metadata_album_artist_name?: unknown };

function readZip(bytes: Uint8Array): Promise<string[]> {
  return new Promise((resolve, reject) => {
    const options = { filter: ({ name }: { name: string }) => HISTORY_FILE.test(name) };
    unzip(bytes, options, (error, entries) => {
      if (error) reject(new TasteFileError("That zip file could not be read."));
      else resolve(Object.values(entries).map((entry) => new TextDecoder().decode(entry)));
    });
  });
}

async function readHistory(file: File): Promise<string[]> {
  if (file.name.toLowerCase().endsWith(".zip")) {
    return readZip(new Uint8Array(await file.arrayBuffer()));
  }
  return [await file.text()];
}

function parsePlays(text: string): Play[] {
  try {
    const plays: unknown = JSON.parse(text);
    if (Array.isArray(plays)) return plays;
  } catch {
    // Falls through to the shared message below.
  }
  throw new TasteFileError(NOT_A_HISTORY_FILE);
}

// Runs on this device and sends nothing. Only the Artist names it returns ever leave.
export async function artistsFromHistory(files: File[]): Promise<string[]> {
  const listening = new Map<string, number>();
  const texts = (await Promise.all(files.map(readHistory))).flat();
  for (const text of texts) {
    for (const { ms_played, master_metadata_album_artist_name: artist } of parsePlays(text)) {
      // Podcasts and audiobooks have no Artist.
      if (typeof artist !== "string" || typeof ms_played !== "number") continue;
      listening.set(artist, (listening.get(artist) ?? 0) + ms_played);
    }
  }
  if (listening.size === 0) throw new TasteFileError(NOT_A_HISTORY_FILE);
  const mostPlayed = [...listening].sort(([, a], [, b]) => b - a).map(([artist]) => artist);
  return tidy(mostPlayed).slice(0, HISTORY_SIZE);
}

function tidy(names: string[]): string[] {
  const unique = new Map<string, string>();
  for (const name of names.map((raw) => raw.trim())) {
    const key = name.toLowerCase();
    if (name && name.length <= LONGEST_NAME && !unique.has(key)) unique.set(key, name);
  }
  return [...unique.values()];
}

function artistColumn(text: string): string[] | null {
  const { data, meta } = Papa.parse<Record<string, string>>(text, {
    header: true,
    skipEmptyLines: true,
  });
  const column = meta.fields?.find((field) => ARTIST_COLUMNS.includes(field.trim().toLowerCase()));
  return column === undefined ? null : data.map((row) => row[column] ?? "");
}

// A name can hold a comma, so commas only separate names when everything is on one line.
export function artistsFromList(text: string): string[] {
  const lines = text.split(/\r?\n/).filter((line) => line.trim());
  const names = artistColumn(text) ?? (lines.length === 1 ? lines[0].split(",") : lines);
  const artists = tidy(names).slice(0, LIST_SIZE);
  if (artists.length === 0) throw new TasteFileError("We could not find any Artists in that list.");
  return artists;
}
