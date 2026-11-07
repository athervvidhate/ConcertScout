import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { NearbyConcerts } from "@/components/nearby";

const chicago = { name: "Chicago, IL", lat: 41.87, lon: -87.62 };
const concert = {
  id: "1",
  name: "Khruangbin Live",
  url: "https://www.ticketmaster.com/event/1",
  artists: [{ name: "Khruangbin" }],
  date: "2026-11-20",
  venue: "The Salt Shed",
};

function stubApi() {
  const fetchStub = vi.fn(async (url: string) => {
    if (url.includes("/places")) return Response.json({ places: [chicago] });
    return Response.json({ concerts: [concert] });
  });
  vi.stubGlobal("fetch", fetchStub);
  return fetchStub;
}

beforeEach(() => localStorage.clear());

describe("NearbyConcerts", () => {
  it("makes no request until the visitor chooses a place", async () => {
    const fetchStub = stubApi();
    const geolocation = { getCurrentPosition: vi.fn() };
    vi.stubGlobal("navigator", { ...navigator, geolocation });

    render(<NearbyConcerts />);
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(fetchStub).not.toHaveBeenCalled();
    expect(geolocation.getCurrentPosition).not.toHaveBeenCalled();
  });

  it("uses browser location only after the button is pressed", async () => {
    const fetchStub = stubApi();
    const getCurrentPosition = vi.fn((success: PositionCallback) =>
      success({ coords: { latitude: 41.87, longitude: -87.62 } } as GeolocationPosition),
    );
    vi.stubGlobal("navigator", { ...navigator, geolocation: { getCurrentPosition } });

    render(<NearbyConcerts />);
    await userEvent.click(screen.getByRole("button", { name: "Use my location" }));

    const link = await screen.findByRole("link", { name: "Khruangbin" });
    expect(link.getAttribute("href")).toBe(concert.url);
    expect(fetchStub.mock.calls[0][0]).toContain("/nearby?lat=41.87&lon=-87.62");
  });

  it("says so when the visitor refuses location", async () => {
    stubApi();
    const getCurrentPosition = vi.fn((_: PositionCallback, failure: PositionErrorCallback) =>
      failure({ code: 1 } as GeolocationPositionError),
    );
    vi.stubGlobal("navigator", { ...navigator, geolocation: { getCurrentPosition } });

    render(<NearbyConcerts />);
    await userEvent.click(screen.getByRole("button", { name: "Use my location" }));

    expect(await screen.findByText(/Choose a place instead/)).toBeTruthy();
  });

  it("loads Concerts for a place chosen on an earlier visit", async () => {
    localStorage.setItem("concert-scout-place", JSON.stringify(chicago));
    stubApi();

    render(<NearbyConcerts />);

    expect(await screen.findByRole("link", { name: "Khruangbin" })).toBeTruthy();
  });

  it("looks places up on the API, so the Geoapify key stays on the server", async () => {
    const fetchStub = stubApi();

    render(<NearbyConcerts />);
    await userEvent.type(screen.getByLabelText("Show Concerts near a place"), "Chi");

    await waitFor(() => expect(fetchStub.mock.calls.some(([url]) => url.includes("/places?text=Chi"))).toBe(true));
    expect(fetchStub.mock.calls.every(([url]) => url.startsWith("http://127.0.0.1:8000"))).toBe(true);
  });

  it("shows the API's message when nearby Concerts fail", async () => {
    const message = "Ticketmaster is not responding. Try again in a minute.";
    localStorage.setItem("concert-scout-place", JSON.stringify(chicago));
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ code: "x", message }, { status: 503 })));

    render(<NearbyConcerts />);

    expect(await screen.findByText(message)).toBeTruthy();
  });
});
