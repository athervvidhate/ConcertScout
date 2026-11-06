import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { SavedConcerts } from "@/components/saved-concerts";
import { saveConcert } from "@/lib/saved";

const concert = { url: "https://x", artists: [{ name: "Ahead" }], venue: "Metro" };

beforeEach(() => {
  localStorage.clear();
  vi.setSystemTime(new Date(2026, 10, 5, 12));
  saveConcert({ concert: { ...concert, id: "a", name: "Ahead", date: "2026-11-20" }, reason: "Fit" });
  saveConcert({
    concert: { ...concert, id: "b", name: "Gone", artists: [{ name: "Gone" }], date: "2026-11-01" },
  });
  vi.useRealTimers();
});

it("lists upcoming saved Concerts, hides past ones and removes on request", async () => {
  vi.setSystemTime(new Date(2026, 10, 5, 12));
  render(<SavedConcerts />);

  expect(screen.getByRole("heading", { name: "Ahead" })).toBeTruthy();
  expect(screen.queryByRole("heading", { name: "Gone" })).toBeNull();

  await userEvent.click(screen.getByRole("button", { name: "Remove" }));

  expect(screen.getByText(/Nothing saved yet/)).toBeTruthy();
  vi.useRealTimers();
});
