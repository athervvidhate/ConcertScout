import { expect, test, type Page } from "@playwright/test";

import { API_URL } from "./ports";

test.use({ reducedMotion: "reduce" });

const VIDEO = "contractVid";
// Contract Artist has an official live session; Second Contract Artist has none.
const WATCH = "Watch Live performance of Contract Artist";
const STOP = "Stop watching Contract Artist live";

async function openTicket(page: Page, rank = 0) {
  await page.goto("/");
  await page.getByRole("textbox", { name: "Search", exact: true }).fill("UKG in SF");
  await expect(page.getByRole("button", { name: "Search", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.locator(".card-open").nth(rank).waitFor({ state: "visible" });
  await page.locator(".card-open").nth(rank).click();
  const ticket = page.locator(".ticket-dialog");
  await expect(ticket).toHaveCSS("opacity", "1");
  return ticket;
}

function trackYouTube(page: Page) {
  const requests: string[] = [];
  page.on("request", (request) => {
    if (/youtube|ytimg|googlevideo/.test(new URL(request.url()).hostname)) requests.push(request.url());
  });
  return requests;
}

async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

test("Watch Live is the only thing that loads YouTube, and opens at the peak moment", { tag: "@phone" }, async ({ page, isMobile }) => {
  const youtube = trackYouTube(page);
  await page.route("https://www.youtube-nocookie.com/**", (route) =>
    route.fulfill({ contentType: "text/html", body: "<title>Player stand-in</title>" }),
  );
  const ticket = await openTicket(page);
  const watch = ticket.getByRole("button", { name: WATCH });
  await expect(watch).toBeVisible();
  await page.waitForTimeout(500);
  expect(youtube).toEqual([]);
  expect(await page.context().cookies()).toEqual([]);
  const before = (await ticket.boundingBox())!;

  if (isMobile) await watch.tap();
  else {
    await watch.focus();
    await page.keyboard.press("Enter");
  }
  const player = ticket.locator("iframe");
  await expect(player).toHaveAttribute("src", `https://www.youtube-nocookie.com/embed/${VIDEO}?start=252&rel=0`);
  await expect(player).toHaveAttribute("title", "Contract Artist live: Contract Artist: Live at Source Hall");
  await expect(player).toHaveAttribute("allow", /encrypted-media/);
  await expect(ticket.locator(".watch-label")).toHaveText("Contract Sessions · jumps to 4:12");
  const stop = ticket.getByRole("button", { name: STOP });
  await expect(stop).toBeFocused();
  await expect(stop).toHaveAttribute("aria-pressed", "true");
  await expect.poll(() => youtube).toEqual([`https://www.youtube-nocookie.com/embed/${VIDEO}?start=252&rel=0`]);

  // The player takes the photograph's place, in the same box, at YouTube's minimum size, and the
  // Ticket keeps its size.
  const box = (await player.boundingBox())!;
  expect(box.width).toBeGreaterThanOrEqual(200);
  expect(box.height).toBeGreaterThanOrEqual(200);
  const stage = (await ticket.locator(".watch-stage").boundingBox())!;
  const media = (await ticket.locator(".dialog-media").boundingBox())!;
  expect(stage).toEqual(media);
  const during = (await ticket.boundingBox())!;
  expect(during.width).toBe(before.width);
  if (!isMobile) expect(during.height).toBe(before.height);
  // Nothing of ours sits on the player, Close included.
  const close = (await ticket.getByRole("button", { name: "Close Ticket" }).boundingBox())!;
  const apart =
    close.x >= box.x + box.width || close.x + close.width <= box.x ||
    close.y >= box.y + box.height || close.y + close.height <= box.y;
  expect(apart).toBe(true);
  await noOverflow(page);

  await stop.press("Enter");
  await expect(player).toHaveCount(0);
  await watch.press("Enter");
  await expect(player).toBeVisible();
  // Focus stayed on the button, so Escape still closes the Ticket.
  await page.keyboard.press("Escape");
  await expect(ticket).toHaveCount(0);
});

test("an Artist with no official live performance gets a plain line instead of a player", async ({ page }) => {
  const youtube = trackYouTube(page);
  const ticket = await openTicket(page, 1);
  await ticket.getByRole("button", { name: "Watch Live performance of Second Contract Artist" }).click();
  await expect(ticket.getByRole("status")).toHaveText("No official live performance by Second Contract Artist to show yet.");
  await expect(ticket.locator("iframe")).toHaveCount(0);
  expect(youtube).toEqual([]);
});

test("a lookup that fails says so and still lets the visitor stop", async ({ page }) => {
  await page.route(`${API_URL}/artist/live-clip?*`, (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ code: "live_clips_limit", message: "Live clips have reached their limit for today. Try again tomorrow." }),
    }),
  );
  const ticket = await openTicket(page);
  await ticket.getByRole("button", { name: WATCH }).click();
  await expect(ticket.getByRole("alert")).toHaveText("Live clips have reached their limit for today. Try again tomorrow.");
  await ticket.getByRole("button", { name: STOP }).click();
  await expect(ticket.locator(".watch-stage")).toHaveCount(0);
});

test("Listen and Watch Live take turns in the same box", async ({ page }) => {
  await page.route("https://www.youtube-nocookie.com/**", (route) =>
    route.fulfill({ contentType: "text/html", body: "<title>Player stand-in</title>" }),
  );
  const ticket = await openTicket(page);
  await ticket.getByRole("button", { name: "Listen to Contract Artist" }).click();
  await expect(ticket.locator(".listen-stage")).toHaveCount(1);
  await ticket.getByRole("button", { name: WATCH }).click();
  await expect(ticket.locator(".watch-player")).toBeVisible();
  await expect(ticket.locator(".listen-stage")).toHaveCount(1);
  await expect(ticket.getByRole("button", { name: "Listen to Contract Artist" })).toHaveAttribute("aria-pressed", "false");
  await ticket.getByRole("button", { name: "Listen to Contract Artist" }).click();
  await expect(ticket.locator(".watch-player")).toHaveCount(0);
  await expect(ticket.getByRole("button", { name: WATCH })).toHaveAttribute("aria-pressed", "false");
});
