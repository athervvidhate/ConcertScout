import { expect, test, type Page } from "@playwright/test";

const reading = {
  place: "New York",
  artists: ["Floating Points"],
  genres: ["Dance/Electronic"],
};

const undergroundPicks = [
  {
    concert: {
      id: "venue:nowadays:abc123",
      name: "Floating Points: All Night Long",
      source: "venue_calendar",
      artists: [{ name: "Floating Points", mbid: "mbid-fp" }],
      date: "2027-06-12",
      time: "22:00:00",
      time_zone: "America/New_York",
      venue: "Nowadays",
      city: "Queens",
      region: "NY",
      price: { min: 25, max: 35, currency: "USD" },
      url: "https://nowadays.nyc/events/floating-points",
      image: "/spotify-logo-white.svg",
    },
    reason: "Confirmed underground club calendar set with deep analog house and breaks.",
    score: 3,
    grade: "seed",
  },
  {
    concert: {
      id: "eventbrite:998877",
      name: "Late Night Warehouse Sessions",
      source: "eventbrite",
      sold_out: true,
      artists: [],
      date: "2027-06-13",
      time: "23:00:00",
      time_zone: "America/New_York",
      venue: "Public Records",
      city: "Brooklyn",
      region: "NY",
      price: { min: 20, max: 20, currency: "USD" },
      url: "https://www.eventbrite.com/e/998877",
      image: "/spotify-logo-white.svg",
    },
    reason: "Coming up nearby",
  },
];

function sse(recommendations: unknown[]) {
  return [
    ["status", { step: "interpret", message: "Reading your Search" }],
    ["reading", reading],
    ["candidates", { names: ["Floating Points"], total: 2 }],
    ["poster", { recommendations }],
    ["done", {}],
  ]
    .map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
    .join("");
}

async function runSearch(page: Page) {
  await page.route("**/search", (route) =>
    route.fulfill({
      contentType: "text/event-stream",
      body: sse(undergroundPicks),
    }),
  );
  await page.goto("/");
  await page
    .getByRole("textbox", { name: "Search", exact: true })
    .fill("Underground electronic in New York");
  await page.getByRole("button", { name: "Search", exact: true }).click();
}

for (const theme of ["light", "dark"] as const) {
  test(`underground room and sold-out curated promoter render cleanly in ${theme} mode`, async ({
    page,
  }, info) => {
    await page.emulateMedia({ reducedMotion: "reduce", colorScheme: theme });
    await runSearch(page);

    // Grid cards show honest source and sold-out badges with zero overflow.
    await expect(page.locator(".concerts-grid .concert-card")).toHaveCount(2);
    await expect(
      page.locator('.concerts-grid .underground-badge[data-source="venue_calendar"]'),
    ).toHaveText("Underground room");
    await expect(
      page.locator('.concerts-grid .underground-badge[data-source="eventbrite"]'),
    ).toHaveText("Curated promoter");
    await expect(page.locator(".concerts-grid .sold-out-badge")).toHaveText("Sold out");

    const gridOverflow = await page
      .locator(".concerts-grid .concert-card")
      .evaluateAll((cards) =>
        cards.some((card) => {
          const box = card.getBoundingClientRect();
          const date = card.querySelector(".card-date")!.getBoundingClientRect();
          const body = card.querySelector(".card-body")!.getBoundingClientRect();
          return (
            body.top < date.bottom + 4 ||
            body.bottom > box.bottom + 1 ||
            body.left < box.left ||
            body.right > box.right
          );
        }),
      );
    expect(gridOverflow).toBe(false);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    ).toBe(true);

    // List view shows the exact same honest badges with zero horizontal overflow.
    await page.getByRole("button", { name: "List view" }).click();
    await expect(page.locator(".concerts-list .concert-card")).toHaveCount(2);
    await expect(
      page.locator('.concerts-list .underground-badge[data-source="venue_calendar"]'),
    ).toHaveText("Underground room");
    await expect(
      page.locator('.concerts-list .underground-badge[data-source="eventbrite"]'),
    ).toHaveText("Curated promoter");
    await expect(page.locator(".concerts-list .sold-out-badge")).toHaveText("Sold out");
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    ).toBe(true);

    // Confirmed venue_calendar Ticket shows "Underground room" and preserves desktop fit.
    await page
      .getByRole("button", { name: "Open Ticket for Floating Points", exact: true })
      .click();
    const roomDialog = page.getByRole("dialog", {
      name: "Ticket for Floating Points",
      exact: true,
    });
    await expect(roomDialog.locator(".underground-badge")).toHaveText("Underground room");
    await expect(roomDialog.locator(".sold-out-badge")).toHaveCount(0);
    if (info.project.name === "desktop") {
      for (const pane of [".dialog-details", ".ticket-main"]) {
        expect(
          await roomDialog
            .locator(pane)
            .evaluate((el) => el.scrollHeight - el.clientHeight),
        ).toBeLessThanOrEqual(1);
      }
    }
    await page.keyboard.press("Escape");

    // Non-Lineup Eventbrite Ticket shows "Curated promoter" + "Sold out", keeps plain title (no
    // invented Artist panel or Listen button), preserves source Tickets link and desktop fit.
    await page
      .getByRole("button", {
        name: "Open Ticket for Late Night Warehouse Sessions",
        exact: true,
      })
      .click();
    const ebDialog = page.getByRole("dialog", {
      name: "Ticket for Late Night Warehouse Sessions",
      exact: true,
    });
    await expect(ebDialog.locator(".underground-badge")).toHaveText("Curated promoter");
    await expect(ebDialog.locator(".sold-out-badge")).toHaveText("Sold out");
    await expect(ebDialog.locator(".artist-name")).toHaveCount(0);
    await expect(
      ebDialog.getByRole("link", { name: "Tickets for Late Night Warehouse Sessions" }),
    ).toHaveAttribute("href", "https://www.eventbrite.com/e/998877");
    if (info.project.name === "desktop") {
      for (const pane of [".dialog-details", ".ticket-main"]) {
        expect(
          await ebDialog
            .locator(pane)
            .evaluate((el) => el.scrollHeight - el.clientHeight),
        ).toBeLessThanOrEqual(1);
      }
    }
    await page.keyboard.press("Escape");
  });
}
