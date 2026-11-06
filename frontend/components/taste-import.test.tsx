import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TasteImport } from "@/components/taste-import";

function stubImport(status: number, body: unknown) {
  const fetchStub = vi.fn(async () => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetchStub);
  return fetchStub;
}

async function importFrom(source: string, username: string) {
  const user = userEvent.setup();
  render(<TasteImport />);
  await user.click(screen.getByText("Import your Taste"));
  await user.selectOptions(screen.getByRole("combobox", { name: "From" }), source);
  await user.type(screen.getByRole("textbox", { name: "Username" }), username);
  await user.click(screen.getByRole("button", { name: "Import" }));
  return user;
}

describe("TasteImport", () => {
  beforeEach(() => localStorage.clear());

  it("keeps an imported Taste on this device and shows where it came from", async () => {
    const fetchStub = stubImport(200, { artists: ["Khruangbin", "Tyler Childers"] });
    await importFrom("ListenBrainz", "some one");

    expect(await screen.findByText(/Using 2 Artists from ListenBrainz/)).toBeTruthy();
    const [url, init] = fetchStub.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8000/taste/listenbrainz");
    expect(init.body).toBe(JSON.stringify({ username: "some one" }));
    expect(JSON.parse(localStorage.getItem("concert-scout-taste") ?? "")).toEqual({
      source: "listenbrainz",
      username: "some one",
      artists: ["Khruangbin", "Tyler Childers"],
    });
  });

  it("removes the imported Taste", async () => {
    stubImport(200, { artists: ["Khruangbin"] });
    const user = await importFrom("Last.fm", "someone");

    await user.click(await screen.findByRole("button", { name: "Remove" }));

    expect(localStorage.getItem("concert-scout-taste")).toBeNull();
    expect(screen.getByText("Import your Taste")).toBeTruthy();
  });

  it("shows a clear error for an unknown username and keeps nothing", async () => {
    const message = "We could not find that Last.fm username. Check the spelling.";
    stubImport(404, { code: "taste_user_not_found", message });
    await importFrom("Last.fm", "nobody");

    expect((await screen.findByRole("alert")).textContent).toBe(message);
    expect(localStorage.getItem("concert-scout-taste")).toBeNull();
  });

  it("says so when the API cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("failed")));
    await importFrom("Last.fm", "someone");

    expect((await screen.findByRole("alert")).textContent).toContain("not responding");
  });
});
