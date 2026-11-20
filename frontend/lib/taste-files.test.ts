import { zipSync, strToU8 } from "fflate";
import { describe, expect, it } from "vitest";

import {
  artistsFromHistory,
  artistsFromList,
  artistsFromPlaylistFiles,
  parsePlaylistExport,
  TasteFileError,
} from "@/lib/taste-files";

const play = (artist: string | null, ms: number) => ({
  ms_played: ms,
  master_metadata_album_artist_name: artist,
});

const jsonFile = (name: string, body: unknown) =>
  new File([JSON.stringify(body)], name, { type: "application/json" });

const textFile = (name: string, body: string, type = "text/csv") =>
  new File([body], name, { type });

describe("artistsFromHistory", () => {
  it("sums listening time across files and orders Artists by it", async () => {
    const files = [
      jsonFile("Streaming_History_Audio_2020_0.json", [play("Bonobo", 10), play("Khruangbin", 30)]),
      jsonFile("Streaming_History_Audio_2021_1.json", [play("Bonobo", 25)]),
    ];

    expect(await artistsFromHistory(files)).toEqual(["Bonobo", "Khruangbin"]);
  });

  it("skips podcasts, which have no Artist", async () => {
    const file = jsonFile("h.json", [play(null, 999), play("Bonobo", 1)]);

    expect(await artistsFromHistory([file])).toEqual(["Bonobo"]);
  });

  it("keeps the top 50", async () => {
    const plays = Array.from({ length: 60 }, (_, n) => play(`Artist ${n}`, n));

    const artists = await artistsFromHistory([jsonFile("h.json", plays)]);

    expect(artists).toHaveLength(50);
    expect(artists[0]).toBe("Artist 59");
  });

  it("reads the history files inside Spotify's zip and ignores the rest", async () => {
    const zip = zipSync({
      "Spotify Extended Streaming History/Streaming_History_Audio_2020_0.json": strToU8(
        JSON.stringify([play("Bonobo", 5)]),
      ),
      "Spotify Extended Streaming History/ReadMeFirst.pdf": strToU8("not json"),
      "Spotify Extended Streaming History/Streaming_History_Video_2020.json": strToU8("not json"),
    });

    const file = new File([zip.slice().buffer], "my_spotify_data.zip");

    expect(await artistsFromHistory([file])).toEqual(["Bonobo"]);
  });

  it.each([
    ["broken JSON", new File(["{nope"], "h.json")],
    ["JSON of another shape", jsonFile("h.json", { plays: [] })],
    ["a list with no Artists", jsonFile("h.json", [{ song: "x" }])],
    ["a file that is not a zip", new File(["nope"], "h.zip")],
    ["a zip with no history", new File([zipSync({ "a.txt": strToU8("x") }).slice().buffer], "h.zip")],
  ])("gives a clear error for %s", async (_, file) => {
    await expect(artistsFromHistory([file])).rejects.toBeInstanceOf(TasteFileError);
  });
});

describe("artistsFromList", () => {
  it("reads one Artist per line, keeping commas inside a name", () => {
    expect(artistsFromList("Earth, Wind & Fire\n Khruangbin \n\nBonobo\r\n")).toEqual([
      "Earth, Wind & Fire",
      "Khruangbin",
      "Bonobo",
    ]);
  });

  it("reads comma-separated text on one line", () => {
    expect(artistsFromList("Khruangbin, Bonobo,Rhye")).toEqual(["Khruangbin", "Bonobo", "Rhye"]);
  });

  it("reads a CSV's Artist column, with quoted commas", () => {
    const csv = 'Track,Artist Name,Plays\nA,"Earth, Wind & Fire",3\nB,Bonobo,2\n';

    expect(artistsFromList(csv)).toEqual(["Earth, Wind & Fire", "Bonobo"]);
  });

  it("drops repeats whatever their case", () => {
    expect(artistsFromList("Bonobo\nbonobo\nBONOBO")).toEqual(["Bonobo"]);
  });

  it("caps the list at 100 names and drops an overlong line", () => {
    const names = ["x".repeat(201), ...Array.from({ length: 120 }, (_, n) => `Artist ${n}`)];

    const artists = artistsFromList(names.join("\n"));

    expect(artists).toHaveLength(100);
    expect(artists[0]).toBe("Artist 0");
  });

  it("gives a clear error for an empty list", () => {
    expect(() => artistsFromList(" \n , \n")).toThrow(TasteFileError);
  });
});

describe("Exportify and TuneMyMusic presets", () => {
  it("parses an Exportify CSV with semicolon-delimited Artist Name(s), BOM, and ranks by frequency", () => {
    const exportifyCsv = [
      "\uFEFFTrack URI,Track Name,Artist URI(s),Artist Name(s),Album Name,Added At",
      "spotify:track:1,White Gloves,spotify:artist:1,Khruangbin,The Universe Smiles Upon You,2026-01-01",
      'spotify:track:2,Texas Sun,"spotify:artist:1; spotify:artist:2","Khruangbin; Leon Bridges",Texas Sun,2026-01-02',
      'spotify:track:3,Latch,"spotify:artist:3; spotify:artist:4","Disclosure; Sam Smith",Settle,2026-01-03',
      'spotify:track:4,Midnight,"spotify:artist:1; spotify:artist:5","khruangbin; Earth, Wind & Fire",Live,2026-01-04',
      'spotify:track:5,Omen,"spotify:artist:3; spotify:artist:4","Disclosure; Sam Smith",Caracal,2026-01-05',
    ].join("\n");

    const parsed = parsePlaylistExport(exportifyCsv);
    expect(parsed.format).toBe("exportify");
    expect(parsed.trackCount).toBe(5);
    expect(parsed.artists).toEqual([
      "Khruangbin",
      "Disclosure",
      "Sam Smith",
      "Leon Bridges",
      "Earth, Wind & Fire",
    ]);
  });

  it("parses newer Exportify comma-delimited Artist Name(s) while preserving single-artist commas via Artist URI(s)", () => {
    const exportifyCsv = [
      "Track URI,Track Name,Artist URI(s),Artist Name(s),Album Name",
      'spotify:track:1,September,spotify:artist:ewf,"Earth, Wind & Fire",Best Of',
      'spotify:track:2,See You Again,spotify:artist:tyler,"Tyler, The Creator",Flower Boy',
      'spotify:track:3,Marea,"spotify:artist:fred, spotify:artist:tbm","Fred again.., The Blessed Madonna",Actual Life',
      'spotify:track:4,Delilah,spotify:artist:fred,Fred again..,Actual Life 3',
    ].join("\n");

    const parsed = parsePlaylistExport(exportifyCsv);
    expect(parsed.format).toBe("exportify");
    expect(parsed.artists).toEqual([
      "Fred again..",
      "Earth, Wind & Fire",
      "Tyler, The Creator",
      "The Blessed Madonna",
    ]);
  });

  it("parses a real TuneMyMusic CSV fixture, ranks by frequency, and discards track metadata", () => {
    const tmmCsv = [
      "\uFEFFTrack name,Artist name,Album,Playlist name,Type,ISRC,Spotify - id",
      "Let It Happen,Tame Impala,Currents,Liked Songs,Track,AUUM71500297,2X485T9Z5Ly0xyaghN73ed",
      "Borderline,Tame Impala,The Slow Rush,Liked Songs,Track,AUUM71900999,5hM5arv9KDbCHS0k9uqwjr",
      "White Gloves,Khruangbin,The Universe Smiles Upon You,Liked Songs,Track,GB123456,1abc",
      'September,"Earth, Wind & Fire",The Best Of,Liked Songs,Track,US123456,2def',
      'Marea,"Fred again..; The Blessed Madonna",Actual Life,Liked Songs,Track,UK123456,3ghi',
      "Breathe Deeper,tame impala,The Slow Rush,Liked Songs,Track,AUUM72000111,4jkl",
    ].join("\n");

    const parsed = parsePlaylistExport(tmmCsv);
    expect(parsed.format).toBe("tunemymusic-csv");
    expect(parsed.trackCount).toBe(6);
    expect(parsed.artists).toEqual([
      "Tame Impala",
      "Khruangbin",
      "Earth, Wind & Fire",
      "Fred again..",
      "The Blessed Madonna",
    ]);
    expect(JSON.stringify(parsed)).not.toMatch(/AUUM71500297|Currents|2X485T9Z5Ly0xyaghN73ed/);
  });

  it("parses a TuneMyMusic TXT export (Artist - Track lines) and discards track titles", () => {
    const tmmTxt = [
      "Bonobo - Kerala",
      "Khruangbin - White Gloves",
      "Bonobo – Cirrus",
      "Fred again.. — Delilah (pull me out of this)",
      "bonobo - Linked",
      "Khruangbin; Leon Bridges - Texas Sun",
    ].join("\n");

    const parsed = parsePlaylistExport(tmmTxt);
    expect(parsed.format).toBe("tunemymusic-txt");
    expect(parsed.trackCount).toBe(6);
    expect(parsed.artists).toEqual(["Bonobo", "Khruangbin", "Fred again..", "Leon Bridges"]);
    expect(JSON.stringify(parsed)).not.toMatch(/Kerala|White Gloves|Cirrus|Delilah|Texas Sun/);
  });

  it("combines multiple Exportify/TuneMyMusic files client-side and caps at top 50 Artists", async () => {
    const rows = Array.from({ length: 60 }, (_, idx) => {
      const name = `Artist ${idx}`;
      return `spotify:track:${idx},Song ${idx},spotify:artist:${idx},${name},Album`;
    });
    const fileA = textFile(
      "liked_songs.csv",
      ["Track URI,Track Name,Artist URI(s),Artist Name(s),Album Name", ...rows].join("\n"),
    );
    const fileB = textFile(
      "favorites.txt",
      ["Artist 59 - Song A", "Artist 59 - Song B", "Artist 42 - Song C"].join("\n"),
      "text/plain",
    );

    const parsed = await artistsFromPlaylistFiles([fileA, fileB]);
    expect(parsed.format).toBe("exportify");
    expect(parsed.artists).toHaveLength(50);
    expect(parsed.artists[0]).toBe("Artist 59");
    expect(parsed.artists[1]).toBe("Artist 42");
  });

  it("rejects Spotify history zip/json dropped into the CSV preset uploader with guidance", async () => {
    await expect(
      artistsFromPlaylistFiles([jsonFile("Streaming_History_Audio_2025.json", [])]),
    ).rejects.toThrow(/Spotify history file/);
  });
});
