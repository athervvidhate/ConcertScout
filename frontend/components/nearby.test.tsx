import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { NearbyConcerts } from "@/components/nearby";

const place = { lat: 41.87, lon: -87.62 };

describe("NearbyConcerts", () => {
  it("shows the API's message when nearby Concerts fail", async () => {
    const body = { code: "ticketmaster_unavailable", message: "Ticketmaster is not answering." };
    vi.stubGlobal("fetch", vi.fn(async () => Response.json(body, { status: 503 })));
    render(<NearbyConcerts place={place} onClose={() => {}} />);

    expect(await screen.findByText("Ticketmaster is not answering.")).toBeTruthy();
  });

  it("points to the search box when nothing is nearby", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ concerts: [] })));
    render(<NearbyConcerts place={place} onClose={() => {}} />);

    expect(await screen.findByText(/Search a nearby city/)).toBeTruthy();
  });
});
