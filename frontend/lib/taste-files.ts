import { unzip } from "fflate";
import Papa from "papaparse";

const HISTORY_SIZE = 50;
const EXPORT_SIZE = 50;
const LIST_SIZE = 100;
// The API refuses a longer Artist name, so one stray line must not sink the whole list.
const LONGEST_NAME = 200;
const HISTORY_FILE = /Streaming_History_Audio[^/]*\.json$/;
const ARTIST_COLUMNS = ["artist", "artists", "artist name", "artistname"];
const EXPORTIFY_ARTIST_COLUMN = "artist name(s)";
const EXPORTIFY_URI_COLUMN = "artist uri(s)";
const TUNEMYMUSIC_MARKER_COLUMNS = ["playlist name", "spotify - id", "isrc", "type"];
const TUNEMYMUSIC_TRACK_SEPARATOR = /\s+(?:-|–|—)\s+/;

const NOT_A_HISTORY_FILE =
  "That is not a Spotify Extended Streaming History file. Choose the zip or its Streaming_History_Audio JSON files.";
const NOT_A_PLAYLIST_FILE =
  "We could not find any Artists in that file. Export a CSV from Exportify or a CSV/TXT file from TuneMyMusic and try again.";

// A message the visitor can act on, as opposed to an unexpected failure.
export class TasteFileError extends Error {}

export type PlaylistExportFormat =
  | "exportify"
  | "tunemymusic-csv"
  | "tunemymusic-txt"
  | "csv"
  | "list";

export type ParsedPlaylistImport = {
  format: PlaylistExportFormat;
  artists: string[];
  trackCount: number;
};

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

function stripBom(text: string): string {
  return text.startsWith("\uFEFF") ? text.slice(1) : text;
}

function tidy(names: string[]): string[] {
  const unique = new Map<string, string>();
  for (const name of names.map((raw) => raw.trim())) {
    const key = name.toLowerCase();
    if (name && name.length <= LONGEST_NAME && !unique.has(key)) unique.set(key, name);
  }
  return [...unique.values()];
}

type FrequencyEntry = { name: string; count: number; order: number };

function addCount(counts: Map<string, FrequencyEntry>, raw: string): boolean {
  const name = raw.trim();
  if (!name || name.length > LONGEST_NAME) return false;
  const key = name.toLowerCase();
  const existing = counts.get(key);
  if (existing) {
    existing.count += 1;
  } else {
    counts.set(key, { name, count: 1, order: counts.size });
  }
  return true;
}

function rankByFrequency(counts: Map<string, FrequencyEntry>, limit: number): string[] {
  return [...counts.values()]
    .sort((a, b) => b.count - a.count || a.order - b.order)
    .slice(0, limit)
    .map((entry) => entry.name);
}

function splitExportifyArtists(rawArtists: string, rawUris?: string): string[] {
  const trimmed = rawArtists.trim();
  if (!trimmed) return [];
  // Classic Exportify joins multiple Artists with semicolons, which safely preserves commas in names.
  if (trimmed.includes(";")) {
    return trimmed
      .split(";")
      .map((part) => part.trim())
      .filter(Boolean);
  }
  // Newer Exportify joins with ", ". When Artist URI(s) has exactly 1 URI, keep commas in the name.
  if (rawUris) {
    const uriCount = rawUris
      .split(/[;,]/)
      .map((part) => part.trim())
      .filter(Boolean).length;
    if (uriCount === 1) return [trimmed];
  }
  if (trimmed.includes(",")) {
    return trimmed
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean);
  }
  return [trimmed];
}

function splitSemicolonArtists(rawArtists: string): string[] {
  const trimmed = rawArtists.trim();
  if (!trimmed) return [];
  if (trimmed.includes(";")) {
    return trimmed
      .split(";")
      .map((part) => part.trim())
      .filter(Boolean);
  }
  return [trimmed];
}

type CsvExtraction = {
  format: "exportify" | "tunemymusic-csv" | "csv";
  counts: Map<string, FrequencyEntry>;
  trackCount: number;
};

function extractFromCsv(text: string): CsvExtraction | null {
  const cleaned = stripBom(text);
  const { data, meta } = Papa.parse<Record<string, string>>(cleaned, {
    header: true,
    skipEmptyLines: true,
  });
  const fields = meta.fields ?? [];
  if (fields.length === 0) return null;

  const byLower = new Map<string, string>();
  for (const field of fields) {
    const normalized = field.trim().toLowerCase();
    if (!byLower.has(normalized)) byLower.set(normalized, field);
  }

  // Exportify exports an explicit `Artist Name(s)` column.
  const exportifyColumn = byLower.get(EXPORTIFY_ARTIST_COLUMN);
  if (exportifyColumn !== undefined) {
    const uriColumn = byLower.get(EXPORTIFY_URI_COLUMN);
    const counts = new Map<string, FrequencyEntry>();
    let trackCount = 0;
    for (const row of data) {
      const rawArtists = row[exportifyColumn] ?? "";
      const rawUris = uriColumn ? (row[uriColumn] ?? "") : undefined;
      const artists = splitExportifyArtists(rawArtists, rawUris);
      let rowHadArtist = false;
      for (const artist of artists) {
        if (addCount(counts, artist)) rowHadArtist = true;
      }
      if (rowHadArtist) trackCount += 1;
    }
    return { format: "exportify", counts, trackCount };
  }

  const artistColumn = ARTIST_COLUMNS.map((name) => byLower.get(name)).find(
    (field): field is string => field !== undefined,
  );
  if (artistColumn === undefined) return null;

  const hasTrackColumn = byLower.has("track name") || byLower.has("track");
  const hasTuneMyMusicMarker =
    hasTrackColumn &&
    (TUNEMYMUSIC_MARKER_COLUMNS.some((marker) => byLower.has(marker)) || byLower.has("album"));

  const counts = new Map<string, FrequencyEntry>();
  let trackCount = 0;
  for (const row of data) {
    const rawArtists = row[artistColumn] ?? "";
    const artists = hasTuneMyMusicMarker ? splitSemicolonArtists(rawArtists) : [rawArtists];
    let rowHadArtist = false;
    for (const artist of artists) {
      if (addCount(counts, artist)) rowHadArtist = true;
    }
    if (rowHadArtist) trackCount += 1;
  }

  return {
    format: hasTuneMyMusicMarker ? "tunemymusic-csv" : "csv",
    counts,
    trackCount,
  };
}

type TxtExtraction = {
  counts: Map<string, FrequencyEntry>;
  trackCount: number;
};

function extractTuneMyMusicTxt(lines: string[]): TxtExtraction | null {
  let matchedLines = 0;
  const counts = new Map<string, FrequencyEntry>();
  for (const line of lines) {
    const match = TUNEMYMUSIC_TRACK_SEPARATOR.exec(line);
    if (!match || match.index === 0) continue;
    const artistPart = line.slice(0, match.index).trim();
    const trackPart = line.slice(match.index + match[0].length).trim();
    if (!artistPart || !trackPart) continue;
    matchedLines += 1;
    for (const artist of splitSemicolonArtists(artistPart)) {
      addCount(counts, artist);
    }
  }
  if (matchedLines === 0 || matchedLines * 2 < lines.length) return null;
  return { counts, trackCount: matchedLines };
}

export function parsePlaylistExport(text: string, limit: number = EXPORT_SIZE): ParsedPlaylistImport {
  const cleaned = stripBom(text);
  const csv = extractFromCsv(cleaned);
  if (csv) {
    const artists = rankByFrequency(csv.counts, limit);
    if (artists.length === 0) throw new TasteFileError(NOT_A_PLAYLIST_FILE);
    return { format: csv.format, artists, trackCount: csv.trackCount };
  }

  const lines = cleaned
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length === 0) throw new TasteFileError(NOT_A_PLAYLIST_FILE);

  const txt = extractTuneMyMusicTxt(lines);
  if (txt) {
    const artists = rankByFrequency(txt.counts, limit);
    if (artists.length === 0) throw new TasteFileError(NOT_A_PLAYLIST_FILE);
    return { format: "tunemymusic-txt", artists, trackCount: txt.trackCount };
  }

  const names = lines.length === 1 ? lines[0].split(",") : lines;
  const counts = new Map<string, FrequencyEntry>();
  for (const name of names) addCount(counts, name);
  const artists = rankByFrequency(counts, limit);
  if (artists.length === 0) throw new TasteFileError(NOT_A_PLAYLIST_FILE);
  return { format: "list", artists, trackCount: lines.length };
}

// Runs strictly in the browser; raw playlist CSV/TXT files never leave this device.
export async function artistsFromPlaylistFiles(files: File[]): Promise<ParsedPlaylistImport> {
  if (files.length === 0) throw new TasteFileError(NOT_A_PLAYLIST_FILE);

  for (const file of files) {
    const lower = file.name.toLowerCase();
    if (lower.endsWith(".zip") || lower.endsWith(".json")) {
      throw new TasteFileError(
        "That looks like a Spotify history archive. Switch Import from to Spotify history file to use it.",
      );
    }
  }

  const texts = await Promise.all(files.map((file) => file.text()));
  const combined = new Map<string, FrequencyEntry>();
  let totalTracks = 0;
  let detectedFormat: PlaylistExportFormat | null = null;

  for (const text of texts) {
    const cleaned = stripBom(text);
    const csv = extractFromCsv(cleaned);
    if (csv) {
      if (detectedFormat === null || detectedFormat === "list" || detectedFormat === "csv") {
        detectedFormat = csv.format;
      }
      totalTracks += csv.trackCount;
      for (const entry of csv.counts.values()) {
        for (let i = 0; i < entry.count; i += 1) addCount(combined, entry.name);
      }
      continue;
    }

    const lines = cleaned
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    const txt = extractTuneMyMusicTxt(lines);
    if (txt) {
      if (detectedFormat === null || detectedFormat === "list") {
        detectedFormat = "tunemymusic-txt";
      }
      totalTracks += txt.trackCount;
      for (const entry of txt.counts.values()) {
        for (let i = 0; i < entry.count; i += 1) addCount(combined, entry.name);
      }
      continue;
    }

    if (lines.length > 0) {
      detectedFormat ??= "list";
      const names = lines.length === 1 ? lines[0].split(",") : lines;
      for (const name of names) {
        if (addCount(combined, name)) totalTracks += 1;
      }
    }
  }

  const artists = rankByFrequency(combined, EXPORT_SIZE);
  if (artists.length === 0) throw new TasteFileError(NOT_A_PLAYLIST_FILE);
  return { format: detectedFormat ?? "csv", artists, trackCount: totalTracks };
}

// A name can hold a comma, so commas only separate names when everything is on one line.
export function artistsFromList(text: string): string[] {
  const cleaned = stripBom(text);
  const csv = extractFromCsv(cleaned);
  if (csv) {
    const artists = rankByFrequency(csv.counts, LIST_SIZE);
    if (artists.length === 0) throw new TasteFileError("We could not find any Artists in that list.");
    return artists;
  }

  const lines = cleaned.split(/\r?\n/).filter((line) => line.trim());
  const names = lines.length === 1 ? lines[0].split(",") : lines;
  const artists = tidy(names).slice(0, LIST_SIZE);
  if (artists.length === 0) throw new TasteFileError("We could not find any Artists in that list.");
  return artists;
}
