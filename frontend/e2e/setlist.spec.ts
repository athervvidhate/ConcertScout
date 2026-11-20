import { expect, test, type Page } from "@playwright/test";

import { RECORDED_SEARCH as recording } from "./fixtures/khruangbin";

const SETLIST_SUMMARY = {
  artist: "Rhye",
  mbid: "44b57239-610e-4d58-b7d8-55cc1188a56d",
  show_count: 5,
  average_songs: 16,
  encore_shows: 4,
  last_show: {
    date: "2026-10-24",
    venue: "Greek Theatre",
    city: "Berkeley, CA",
  },
  staples: [
    { name: "Open", shows: 5, encore_shows: 0 },
    { name: "The Fall", shows: 5, encore_shows: 0 },
    { name: "Taste", shows: 5, encore_shows: 0 },
    { name: "Song for You", shows: 5, encore_shows: 4 },
    { name: "Last Dance", shows: 4, encore_shows: 0 },
    { name: "3 Days", shows: 4, encore_shows: 0 },
    { name: "Black Rain", shows: 4, encore_shows: 0 },
    { name: "Helpless", shows: 3, encore_shows: 0 },
  ],
  source_url: "https://www.setlist.fm/setlists/rhye-63d86e13.html",
};

async function runRecordedSearch(page: Page) {
  const body = [
    ["reading", recording.reading],
    ["candidates", recording.candidates],
    ["poster", recording.poster],
    ["done", {}],
  ]
    .map(
      ([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`,
    )
    .join("");
  await page.route("**/search", (route) =>
    route.fulfill({ contentType: "text/event-stream", body }),
  );
  await page.goto("/");
  await page
    .getByRole("textbox", { name: "Search", exact: true })
    .fill(recording.text);
  await page.getByRole("button", { name: "Search", exact: true }).click();
}

test("Setlist DNA loads lazily on Ticket without resizing or scrolling, and returns focus", async ({
  page,
}, info) => {
  const setlistRequests: string[] = [];
  await page.route("**/artist/setlist?*", async (route) => {
    setlistRequests.push(route.request().url());
    const response = await route.fetch();
    await route.fulfill({ response, json: SETLIST_SUMMARY });
  });

  await runRecordedSearch(page);
  await page
    .getByRole("button", { name: "Open Ticket for Rhye", exact: true })
    .click();

  const sheet = page.locator(".ticket-dialog");
  await expect(sheet).toHaveAttribute("data-motion-phase", "open");
  // Strictly lazy: Search and opening the Ticket never call /artist/setlist.
  expect(setlistRequests).toEqual([]);

  const before = (await sheet.boundingBox())!;
  const photo = (await sheet.locator(".dialog-photo").boundingBox())!;

  const setlistButton = sheet.getByRole("button", { name: "Setlist" });
  await setlistButton.click();

  const back = sheet.getByRole("button", { name: /^Back to/ });
  await expect(back).toBeFocused();
  await expect.poll(() => setlistRequests.length).toBe(1);

  await expect(sheet.getByText("16 songs avg · last 5 shows · encore in 4 of 5")).toBeVisible();
  await expect(
    sheet.getByText("Last show: Sat, Oct 24, 2026 · Greek Theatre · Berkeley, CA"),
  ).toBeVisible();
  await expect(sheet.locator(".setlist-staples li")).toHaveCount(8);

  // Page through if needed to reach the Setlist.fm attribution link without scrolling.
  const next = sheet.getByRole("button", { name: "Next page" });
  while ((await next.count()) && (await next.isEnabled())) await next.click();
  const credit = sheet.getByRole("link", { name: "Setlist.fm" });
  await expect(credit).toHaveAttribute("href", SETLIST_SUMMARY.source_url);
  await expect(credit).toBeInViewport();

  // Fixed-height and non-scrolling invariants hold.
  const after = (await sheet.boundingBox())!;
  const photoAfter = (await sheet.locator(".dialog-photo").boundingBox())!;
  expect(Math.abs(photoAfter.width - photo.width)).toBeLessThanOrEqual(1);
  expect(Math.abs(photoAfter.height - photo.height)).toBeLessThanOrEqual(1);
  if (info.project.name === "desktop") {
    expect(Math.abs(after.height - before.height)).toBeLessThanOrEqual(1);
    for (const pane of [".dialog-details", ".ticket-main"]) {
      expect(
        await sheet
          .locator(pane)
          .evaluate((el) => el.scrollHeight - el.clientHeight),
      ).toBeLessThanOrEqual(1);
    }
  }
  await expect(sheet.getByRole("button", { name: "Close Ticket" })).toBeInViewport();
  await expect(sheet.getByRole("button", { name: "Save", exact: true })).toBeInViewport();

  // Dark theme and reduced motion keep layout clean with no horizontal overflow.
  await page.evaluate(() => {
    document.documentElement.dataset.mode = "dark";
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    ),
  ).toBeLessThanOrEqual(1);

  await back.click();
  await expect(setlistButton).toBeFocused();
  expect(
    Math.abs((await sheet.boundingBox())!.height - before.height),
  ).toBeLessThanOrEqual(1);
});

test("Artist panel displays Setlist DNA when available and omits it cleanly when missing", async ({
  page,
}) => {
  await page.route("**/artist?*", async (route) => {
    const name = new URL(route.request().url()).searchParams.get("name") ?? "Rhye";
    const response = await route.fetch();
    await route.fulfill({
      response,
      json: { profiles: [{ name, tags: ["soul"], top_tracks: [], similar: [] }] },
    });
  });

  // First test with real setlist data present.
  await page.route("**/artist/setlist?*", async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: SETLIST_SUMMARY });
  });

  await runRecordedSearch(page);
  await page
    .getByRole("button", { name: "Open Ticket for Rhye", exact: true })
    .click();
  const sheet = page.locator(".ticket-dialog");
  await expect(sheet).toHaveAttribute("data-motion-phase", "open");
  await sheet.locator(".artist-name").click();

  const panel = page.getByRole("dialog", { name: "Rhye", exact: true });
  await expect(panel.getByRole("heading", { name: "Recent setlist" })).toBeVisible();
  await expect(panel.getByText("16 songs avg · last 5 shows · encore in 4 of 5")).toBeVisible();
  await expect(panel.getByRole("link", { name: "Setlist.fm" })).toHaveAttribute(
    "href",
    SETLIST_SUMMARY.source_url,
  );

  // Close Artist panel and swap route to empty summary (no Setlist.fm data).
  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);
  await page.unroute("**/artist/setlist?*");
  await page.route("**/artist/setlist?*", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      response,
      json: { artist: "Rhye", show_count: 0, encore_shows: 0, staples: [] },
    });
  });

  await sheet.locator(".artist-name").click();
  await expect(panel).toBeVisible();
  await expect(panel.getByText("soul")).toBeVisible();
  await expect(panel.getByRole("heading", { name: "Recent setlist" })).toHaveCount(0);
  await expect(panel.getByRole("link", { name: "Setlist.fm" })).toHaveCount(0);
});
