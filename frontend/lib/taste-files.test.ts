import { zipSync, strToU8 } from "fflate";
import { describe, expect, it } from "vitest";

import { artistsFromHistory, artistsFromList, TasteFileError } from "@/lib/taste-files";

const play = (artist: string | null, ms: number) => ({
  ms_played: ms,
  master_metadata_album_artist_name: artist,
});

const jsonFile = (name: string, body: unknown) =>
  new File([JSON.stringify(body)], name, { type: "application/json" });

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
