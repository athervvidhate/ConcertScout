import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Search } from "@/components/search";
import type { Concert } from "@/lib/search";
import { keepTaste } from "@/lib/taste";

const full: Concert = {
  id: "1",
  name: "Khruangbin: The Ether Tour",
  url: "https://www.ticketmaster.com/event/1",
  artists: [{ name: "Khruangbin" }],
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

async function searchFor(text: string) {
  const user = userEvent.setup();
  render(<Search />);
  await user.type(screen.getByRole("textbox", { name: "Search" }), text);
  await user.click(screen.getByRole("button", { name: "Find concerts" }));
  return user;
}

const poster = (...concerts: Concert[]) =>
  sse("poster", { recommendations: concerts.map((concert) => ({ concert, reason: "Similar to Khruangbin" })) });

describe("Search", () => {
  beforeEach(() => {
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: true }));
  });
  it("keeps reading the stream after the pool total", async () => {
    stubStream(sse("pool", { total: 1189 }), poster(full), sse("done", {}));

    await searchFor("Chicago");

    await screen.findByRole("link", { name: `Tickets for ${full.name}` });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows the shortlisted names and still waits for the Poster after them", async () => {
    stubStream(
      sse("candidates", { names: ["Khruangbin", "Men I Trust"], total: 2 }),
      poster(full),
      sse("done", {}),
    );

    await searchFor("Something like Khruangbin");

    await screen.findByRole("link", { name: `Tickets for ${full.name}` });
    expect(screen.getByText("Men I Trust")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Khruangbin" })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("caps the shortlisted names at what the loader shows", async () => {
    const names = Array.from({ length: 60 }, (_, n) => `Artist ${n}`);
    stubStream(sse("candidates", { names, total: 60 }), poster(full), sse("done", {}));

    await searchFor("Chicago");

    expect(await screen.findByText("Artist 37")).toBeTruthy();
    expect(screen.queryByText("Artist 38")).toBeNull();
  });

  it("hides Try again when the error says when to come back", async () => {
    stubStream(
      sse("error", {
        code: "ticketmaster_limit",
        message: "Try again tomorrow.",
        retry_after: 3600,
      }),
      sse("done", {}),
    );

    await searchFor("Chicago");

    await screen.findByText("Try again tomorrow.");
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });

  it("posts the text and lists streamed Concerts with their facts", async () => {
    const text = "Something like Khruangbin in Chicago, next two weekends";
    const fetchStub = stubStream(
      sse("status", { step: "interpret", message: "Reading your Search" }),
      sse("interpreted", {
        place: "Chicago",
        start: "2026-11-06",
        end: "2026-11-15",
        artists: ["Khruangbin"],
      }),
      sse("status", { step: "pool", message: "Looking for Concerts near Chicago" }),
      poster(full),
      sse("done", {}),
    );

    await searchFor(text);

    const link = await screen.findByRole("link", { name: `Tickets for ${full.name}` });
    expect(link.getAttribute("href")).toBe(full.url);
    expect(screen.getByText("Nov 20")).toBeTruthy();
    expect(screen.getByText(/The Salt Shed, Chicago, IL, Fri, 7:30 PM/)).toBeTruthy();
    expect(screen.getByText("Similar to Khruangbin")).toBeTruthy();
    expect(screen.getByText(/The Salt Shed, Chicago, IL/)).toBeTruthy();
    expect(document.querySelector(".price")?.textContent).toBe("$45.5 to $120");
    expect(
      screen.getByText("Chicago, Nov 6 to 15"),
    ).toBeTruthy();
    const [url, init] = fetchStub.mock.calls[0];
    expect(url).toBe("http://127.0.0.1:8000/search");
    expect(init.body).toBe(JSON.stringify({ text, token: "test-token", taste: [] }));
  });

  it("leaves a missing time and price blank", async () => {
    stubStream(poster(sparse), sse("done", {}));

    await searchFor("Chicago");

    expect(await screen.findByText("Nov 21")).toBeTruthy();
    expect(screen.queryByText(/PM|AM/)).toBeNull();
    expect(screen.queryByText(/\$/)).toBeNull();
  });

  it("says so when a Search has no Concerts", async () => {
    stubStream(poster(), sse("done", {}));

    await searchFor("Nowhere");

    expect(await screen.findByText(/Nothing qualifies for this Search/)).toBeTruthy();
  });

  it("asks for a new Search instead of a retry when the Search cannot work", async () => {
    const message = "Tell us an Artist, a style or a place.";
    stubStream(sse("error", { code: "needs_taste_or_place", message }), sse("done", {}));

    await searchFor("hello there");

    expect((await screen.findByRole("alert")).textContent).toContain(message);
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });

  it("shows a streamed error and retries the same text", async () => {
    const message = "Ticketmaster is not responding. Try again in a minute.";
    stubStream(sse("error", { code: "ticketmaster_unavailable", message }), sse("done", {}));

    const user = await searchFor("Chicago");
    expect((await screen.findByRole("alert")).textContent).toContain(message);

    const fetchStub = stubStream(poster(full), sse("done", {}));
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("link", { name: `Tickets for ${full.name}` })).toBeTruthy();
    expect(fetchStub.mock.calls[0][1].body).toBe(JSON.stringify({ text: "Chicago", token: "test-token", taste: [] }));
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
    const refusal = { code: "invalid_search", message: "Tell us an Artist, a style or a place." };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(refusal, { status: 422 })));

    await searchFor("Chicago");

    expect((await screen.findByRole("alert")).textContent).toContain(refusal.message);
  });
});

describe("refused Searches", () => {
  function stubRefusal(status: number, body: unknown) {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.includes("/search")) return new Response(JSON.stringify(body), { status });
      return new Response(JSON.stringify({ concerts: [] }));
    }));
  }

  beforeEach(() => localStorage.clear());

  it("sends the bot check token with the Search", async () => {
    const fetchStub = stubStream(sse("done", {}));
    await searchFor("Chicago");

    await screen.findByRole("button", { name: "Find concerts" });
    expect(JSON.parse(fetchStub.mock.calls[0][1].body)).toEqual({ text: "Chicago", token: "test-token", taste: [] });
  });

  it("sends the imported Taste with the Search", async () => {
    keepTaste({ source: "lastfm", username: "someone", artists: ["Khruangbin"] });
    const fetchStub = stubStream(sse("done", {}));
    await searchFor("Chicago");

    await screen.findByRole("button", { name: "Find concerts" });
    expect(JSON.parse(fetchStub.mock.calls[0][1].body).taste).toEqual(["Khruangbin"]);
  });

  it("says when to come back and offers no pointless retry at a limit", async () => {
    stubRefusal(429, {
      code: "visitor_limit",
      message: "You have used this hour's Searches. Try again in 12 minutes.",
      retry_after: 700,
    });
    await searchFor("Chicago");

    expect(await screen.findByText(/Try again in 12 minutes/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });

  it("keeps the home page working when Search stops at the spend cap", async () => {
    stubRefusal(503, {
      code: "budget_reached",
      message: "Concert Scout has used its Search budget for now. Nearby Concerts still work.",
      retry_after: 3600,
    });
    await searchFor("Chicago");

    expect(await screen.findByText(/Search budget/)).toBeTruthy();
    expect(screen.getByRole("region", { name: "Concerts near you" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });
});
