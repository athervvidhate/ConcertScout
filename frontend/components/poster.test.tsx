import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Poster } from "@/components/poster";
import { flyDuration, namesDuration, PICK_READ_MS } from "@/lib/poster-timing";
import type { Recommendation } from "@/lib/search";

const recommendations: Recommendation[] = [{
  concert: {
    id: "real-id", name: "Real Concert", artists: [{ name: "Real Artist" }],
    url: "https://www.ticketmaster.com/event/real-id", venue: "Real Venue",
  },
  reason: "Similar to your seed Artist",
}];
const candidates = { names: ["Real Artist", "Another Artist"], total: 2 };
const animate = vi.fn(() => ({ cancel: vi.fn(), onfinish: null }));
const originalAnimate = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "animate");

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: false }));
  Object.defineProperty(HTMLElement.prototype, "animate", { configurable: true, value: animate });
  animate.mockClear();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  if (originalAnimate) Object.defineProperty(HTMLElement.prototype, "animate", originalAnimate);
  else Reflect.deleteProperty(HTMLElement.prototype, "animate");
});

const advance = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });

describe("Poster presentation", () => {
  it("shows a received Poster even without a candidates event", async () => {
    render(<Poster candidates={null} recommendations={recommendations} hasPoster searching={false} />);
    await advance(0);
    expect(screen.getByRole("link", { name: "Tickets for Real Concert" }).getAttribute("href"))
      .toBe(recommendations[0].concert.url);
    expect(animate).not.toHaveBeenCalled();
  });

  it("finishes names, then picks and fly-in before showing the Ticket", async () => {
    render(<Poster candidates={candidates} recommendations={recommendations} hasPoster searching={false} />);
    await advance(namesDuration(candidates.names.length));
    expect(screen.getByText("1 picks from 2 close matches")).toBeTruthy();
    expect(screen.queryByRole("link")).toBeNull();
    await advance(PICK_READ_MS);
    expect(animate).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("link")).toBeNull();
    await advance(flyDuration(1));
    expect(screen.getByRole("link", { name: "Tickets for Real Concert" })).toBeTruthy();
    expect(screen.getByText("Similar to your seed Artist")).toBeTruthy();
  });

  it("reduced motion shows the Ticket without a fly-in", async () => {
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: true }));
    render(<Poster candidates={candidates} recommendations={recommendations} hasPoster searching={false} />);
    await advance(0);
    expect(screen.getByRole("link", { name: "Tickets for Real Concert" })).toBeTruthy();
    expect(animate).not.toHaveBeenCalled();
  });
});
