import { fireEvent, act, cleanup, render, screen } from "@testing-library/react";
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
const animate = vi.fn<(keyframes: Keyframe[]) => { cancel: () => void; onfinish: null }>(() => ({ cancel: vi.fn(), onfinish: null }));
const originalAnimate = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "animate");

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: false }));
  Object.defineProperty(HTMLElement.prototype, "animate", { configurable: true, value: animate });
  animate.mockClear();
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  if (originalAnimate) Object.defineProperty(HTMLElement.prototype, "animate", originalAnimate);
  else Reflect.deleteProperty(HTMLElement.prototype, "animate");
});

const advance = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });

describe("Poster presentation", () => {
  it("saves and skips from the arrow keys, keeps both, and moves to the next undecided", async () => {
    const second = { ...recommendations[0], concert: { ...recommendations[0].concert, id: "second", artists: [{ name: "Second Artist" }] } };
    render(<Poster candidates={null} recommendations={[...recommendations, second]} hasPoster searching={false} status={null} />);
    await advance(0);

    fireEvent.keyDown(screen.getByRole("button", { name: "Save" }), { key: "ArrowRight" });
    expect(screen.getByRole("button", { name: "Real Artist, saved" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Second Artist" })).toBeTruthy();

    fireEvent.keyDown(screen.getByRole("button", { name: "Save" }), { key: "ArrowLeft" });
    expect(screen.getByRole("button", { name: "Second Artist, skipped" })).toBeTruthy();
    expect(JSON.parse(localStorage.getItem("concert-scout-skipped") ?? "[]")).toEqual(["second"]);
  });

  it("shows the pipeline's real status while the Search runs", () => {
    render(<Poster candidates={null} recommendations={[]} hasPoster={false} searching status="Finding Chicago" />);
    expect(screen.getByText("Finding Chicago")).toBeTruthy();
  });

  it("fades in a pick that has no name on the wall to fly from", async () => {
    render(<Poster candidates={{ names: ["Another Artist"], total: 2 }} recommendations={recommendations} hasPoster searching={false} status={null} />);
    await advance(0);
    await advance(namesDuration(1));
    await advance(PICK_READ_MS);
    const frames = animate.mock.calls.map(([keyframes]) => keyframes as Keyframe[]);
    expect(frames.some((keyframes) => keyframes[0].opacity === 0)).toBe(true);
  });

  it("gives each rank its own Ticket color", async () => {
    const second = { ...recommendations[0], concert: { ...recommendations[0].concert, id: "second", artists: [{ name: "Second Artist" }] } };
    render(<Poster candidates={null} recommendations={[...recommendations, second]} hasPoster searching={false} status={null} />);
    await advance(0);
    expect(document.querySelector(".ticket")?.getAttribute("data-color")).toBe("0");
    fireEvent.click(screen.getByRole("button", { name: "Second Artist" }));
    expect(document.querySelector(".ticket")?.getAttribute("data-color")).toBe("1");
  });

  it("shows a received Poster even without a candidates event", async () => {
    render(<Poster candidates={null} recommendations={recommendations} hasPoster searching={false} status={null} />);
    await advance(0);
    expect(screen.getByRole("link", { name: "Tickets for Real Concert" }).getAttribute("href"))
      .toBe(recommendations[0].concert.url);
    expect(animate).not.toHaveBeenCalled();
  });

  it("finishes names, then picks and fly-in before showing the Ticket", async () => {
    render(<Poster candidates={candidates} recommendations={recommendations} hasPoster searching={false} status={null} />);
    await advance(namesDuration(candidates.names.length));
    expect(screen.getByText("1 picks from 2 close matches")).toBeTruthy();
    expect(screen.queryByRole("link")).toBeNull();
    await advance(PICK_READ_MS);
    expect(animate).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("link")).toBeNull();
    await advance(flyDuration(1));
    expect(screen.getByRole("link", { name: "Tickets for Real Concert" })).toBeTruthy();
    expect(screen.getByText("Similar to your seed Artist")).toBeTruthy();
  });

  it("reduced motion shows the Ticket without a fly-in", async () => {
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: true }));
    render(<Poster candidates={candidates} recommendations={recommendations} hasPoster searching={false} status={null} />);
    await advance(0);
    expect(screen.getByRole("link", { name: "Tickets for Real Concert" })).toBeTruthy();
    expect(animate).not.toHaveBeenCalled();
  });
});

it("keeps duplicate Artists as distinct Concerts and uses 1/2/rest tiers", async () => {
  const picks = Array.from({ length: 5 }, (_, i) => ({ ...recommendations[0], concert: { ...recommendations[0].concert, id: `id-${i}`, venue: `Venue ${i}` } }));
  render(<Poster candidates={null} recommendations={picks} hasPoster searching={false} status={null} />);
  await advance(0);
  const names = screen.getAllByRole("button", { name: /Real Artist.*Venue/ });
  expect(names).toHaveLength(5);
  expect(names.map(n => n.className.match(/tier-\d/)?.[0])).toEqual(["tier-1", "tier-2", "tier-2", "tier-3", "tier-3"]);
  fireEvent.click(names[3]);
  expect(screen.getByText("Venue 3", { selector: ".venue" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(JSON.parse(localStorage.getItem("concert-scout-saved")!)[0].concert.id).toBe("id-3");
  expect(screen.getByRole("status").textContent).toContain("saved on this device");
  fireEvent.click(screen.getByRole("button", { name: "Skip" }));
  expect(screen.getByRole("status").textContent).toContain("skipped");
});

it("does not replay the name reveal when ranking finishes later", async () => {
  const view = render(<Poster candidates={candidates} recommendations={[]} hasPoster={false} searching status={null} />);
  await advance(namesDuration(candidates.names.length) + 2000);
  view.rerender(<Poster candidates={candidates} recommendations={recommendations} hasPoster searching={false} status={null} />);
  await advance(0);
  await advance(PICK_READ_MS);
  expect(animate).toHaveBeenCalled();
});
