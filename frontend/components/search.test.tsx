import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Search } from "@/components/search";
import type { Concert } from "@/lib/search";

const full: Concert = {
  id: "1",
  name: "Khruangbin: The Ether Tour",
  url: "https://www.ticketmaster.com/event/1",
  artists: ["Khruangbin"],
  date: "2026-11-20",
  time: "19:30:00",
  venue: "The Salt Shed",
  city: "Chicago",
  region: "IL",
  price: { min: 45.5, max: 120, currency: "USD" },
};

const sparse: Concert = {
  id: "2",
  name: "Hoyles XL",
  url: "https://www.ticketmaster.com/event/2",
  artists: [],
  date: "2026-11-21",
  venue: "Empty Bottle",
};

function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

function stubStream(...chunks: string[]) {
  const fetchStub = vi.fn().mockResolvedValue(new Response(chunks.join("")));
  vi.stubGlobal("fetch", fetchStub);
  return fetchStub;
}

async function searchFor(city: string) {
  const user = userEvent.setup();
  render(<Search />);
  await user.type(screen.getByLabelText("City"), city);
  await user.click(screen.getByRole("button", { name: "Search" }));
  return user;
}

const poster = (...concerts: Concert[]) =>
  sse("poster", { recommendations: concerts.map((concert) => ({ concert })) });

describe("Search", () => {
  it("posts the city and lists streamed Concerts with their facts", async () => {
    const fetchStub = stubStream(
      sse("status", { step: "pool", message: "Looking for Concerts in Chicago" }),
      poster(full),
      sse("done", {}),
    );

    await searchFor("Chicago");

    const link = await screen.findByRole("link", { name: full.name });
    expect(link.getAttribute("href")).toBe(full.url);
    expect(screen.getByText("Fri, Nov 20, 2026 at 7:30 PM")).toBeTruthy();
    expect(screen.getByText("The Salt Shed, Chicago, IL")).toBeTruthy();
    expect(screen.getByText("$45.50 to $120.00")).toBeTruthy();
    const [url, init] = fetchStub.mock.calls[0];
    expect(url).toBe("http://127.0.0.1:8000/search");
    expect(init.body).toBe(JSON.stringify({ city: "Chicago" }));
  });

  it("leaves a missing time and price blank", async () => {
    stubStream(poster(sparse), sse("done", {}));

    await searchFor("Chicago");

    expect(await screen.findByText("Sat, Nov 21, 2026")).toBeTruthy();
    expect(screen.queryByText(/PM|AM/)).toBeNull();
    expect(screen.queryByText(/\$/)).toBeNull();
  });

  it("says so when a city has no Concerts", async () => {
    stubStream(poster(), sse("done", {}));

    await searchFor("Nowhere");

    expect(await screen.findByText(/No Concerts found in Nowhere/)).toBeTruthy();
  });

  it("shows a streamed error and retries the same city", async () => {
    const message = "Ticketmaster is not responding. Try again in a minute.";
    stubStream(sse("error", { code: "ticketmaster_unavailable", message }), sse("done", {}));

    const user = await searchFor("Chicago");
    expect((await screen.findByRole("alert")).textContent).toContain(message);

    const fetchStub = stubStream(poster(full), sse("done", {}));
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("link", { name: full.name })).toBeTruthy();
    expect(fetchStub.mock.calls[0][1].body).toBe(JSON.stringify({ city: "Chicago" }));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("offers a retry when the stream drops before done", async () => {
    stubStream(sse("status", { step: "pool", message: "Looking" }));

    await searchFor("Chicago");

    expect((await screen.findByRole("alert")).textContent).toContain("connection dropped");
  });

  it("says when the API cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await searchFor("Chicago");

    expect((await screen.findByRole("alert")).textContent).toContain("not responding");
  });

  it("shows the API's message when it refuses a Search", async () => {
    const refusal = { code: "invalid_search", message: "Enter a city." };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(refusal, { status: 422 })));

    await searchFor("Chicago");

    expect((await screen.findByRole("alert")).textContent).toContain("Enter a city.");
  });
});
