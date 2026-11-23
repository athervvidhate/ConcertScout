import { expect, test, type Page } from "@playwright/test";

test.use({ permissions: ["clipboard-read", "clipboard-write"] });

async function assertNoOverflow(page: Page) {
  const fits = await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth);
  expect(fits).toBe(true);
}

test("two friends create a Group Scout room, join as guests, vote live and export .ics", async ({
  page,
  browser,
}) => {
  // Navigate from home via the header menu to verify the Group Scout entry point.
  await page.goto("/");
  await page.getByRole("button", { name: "Menu", exact: true }).click();
  await page.getByRole("menuitem", { name: "Group Scout" }).click();
  await expect(page).toHaveURL(/\/g$/);
  await expect(
    page.getByRole("heading", { name: "Pick a Concert everyone wants to see" }),
  ).toBeVisible();
  await assertNoOverflow(page);

  // Friend 1 (Maya) creates a room without signing in.
  await page.getByLabel("Place").fill("San Francisco, CA");
  await page.getByLabel("Room name (optional)").fill("Bay Area Night Out");
  await page.getByLabel("Your name").fill("Maya");
  await page.getByLabel("Your Taste (Artists you love)").fill("Contract Artist");
  await page.getByRole("button", { name: "Add Artists", exact: true }).click();
  await page.getByRole("button", { name: "Create Group Room" }).click();

  await expect(page).toHaveURL(/\/g\/[A-Za-z0-9_-]{22}$/);
  await expect(page.getByRole("heading", { name: "Bay Area Night Out" })).toBeVisible();
  await expect(page.getByText(/1 of 6 friends/)).toBeVisible();
  await expect(page.getByText("Maya (you)")).toBeVisible();

  // First Concert carries Maya's honest Named badge.
  const firstCard = page.locator('[data-concert-id="contract-one"]');
  await expect(firstCard).toBeVisible();
  await expect(firstCard.getByText("Maya")).toBeVisible();
  await expect(firstCard.getByText("Named")).toBeVisible();

  // Copy invite link.
  await page.getByRole("button", { name: "Copy invite link" }).click();
  await expect(page.getByRole("button", { name: "Link copied" })).toBeVisible();
  const inviteUrl = await page.evaluate(() => navigator.clipboard.readText());
  expect(inviteUrl).toMatch(/\/g\/[A-Za-z0-9_-]{22}$/);

  // Friend 2 (Sam) opens the invite link in an isolated browser context as a guest.
  const samContext = await browser.newContext({
    viewport: page.viewportSize() ?? undefined,
  });
  const samPage = await samContext.newPage();
  await samPage.goto(inviteUrl);

  await expect(samPage.getByRole("heading", { name: "Bay Area Night Out" })).toBeVisible();
  await expect(
    samPage.getByRole("heading", { name: "Join this Group Scout room" }),
  ).toBeVisible();
  await assertNoOverflow(samPage);

  await samPage.getByLabel("Your name").fill("Sam");
  await samPage.getByLabel("Your Taste (Artists)").fill("Second Contract Artist");
  await samPage.getByRole("button", { name: "Add Artists", exact: true }).click();
  await samPage.getByRole("button", { name: "Join room & rank picks" }).click();

  await expect(samPage.getByText(/2 of 6 friends/)).toBeVisible();
  await expect(samPage.getByText("Sam (you)")).toBeVisible();
  await expect(
    samPage.locator('[data-concert-id="contract-two"]').getByText("Sam"),
  ).toBeVisible();
  await expect(
    samPage.locator('[data-concert-id="contract-two"]').getByText("Named"),
  ).toBeVisible();

  // Sam votes In on contract-one and Maybe on contract-two.
  const samCardOne = samPage.locator('[data-concert-id="contract-one"]');
  await samCardOne.getByRole("button", { name: /^In\b/ }).click();
  await expect(samCardOne.getByRole("button", { name: /^In\b/ })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  const samCardTwo = samPage.locator('[data-concert-id="contract-two"]');
  await samCardTwo.getByRole("button", { name: /^Maybe\b/ }).click();
  await expect(samCardTwo.getByRole("button", { name: /^Maybe\b/ })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  // Maya sees Sam join and vote via live sync (Realtime or polling fallback).
  await expect(page.getByText(/2 of 6 friends/)).toBeVisible();
  await expect(firstCard.getByText(/In: Sam/)).toBeVisible();

  // Maya votes In on contract-one -> Consensus highlight!
  await firstCard.getByRole("button", { name: /^In\b/ }).click();
  await expect(firstCard.getByText("Consensus · All In")).toBeVisible();
  await expect(firstCard.getByText(/In: .*Maya/)).toBeVisible();

  // Sort toggle switches to Top voted and back cleanly.
  await page.getByRole("button", { name: "Top voted", exact: true }).click();
  await expect(page.getByRole("button", { name: "Top voted", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.getByRole("button", { name: "Best group fit", exact: true }).click();

  // 1-click .ics calendar export downloads valid RFC 5545 calendar data.
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    firstCard.getByRole("button", { name: /^Add to calendar for/ }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/\.ics$/);
  const stream = await download.createReadStream();
  let ics = "";
  for await (const chunk of stream) ics += chunk.toString();
  expect(ics).toContain("BEGIN:VCALENDAR");
  expect(ics).toContain("SUMMARY:Contract Concert One");

  // Maya can edit her Artists and room search directly inside the room.
  await page.getByRole("button", { name: "Edit my artists" }).click();
  await expect(
    page.getByRole("heading", { name: "Edit your Artists & preferences" }),
  ).toBeVisible();
  await page.getByLabel("Your Taste (Artists)").fill("Third Contract Artist");
  await page.getByRole("button", { name: "Add Artists", exact: true }).click();
  await page.getByRole("button", { name: "Save & re-rank" }).click();
  await expect(page.getByText("2 Artists")).toBeVisible();

  await page.getByRole("button", { name: "Edit search" }).click();
  await expect(
    page.getByRole("heading", { name: "Edit room search" }),
  ).toBeVisible();
  await page.getByLabel("Max ticket price $ (optional)").fill("120");
  await page.getByRole("button", { name: "Update search" }).click();
  await expect(page.getByText("Under $120")).toBeVisible();

  // Verify light and dark themes have zero horizontal overflow at current viewport (1280px & 390px).
  await assertNoOverflow(page);
  await page.getByRole("button", { name: "Menu", exact: true }).click();
  await page.getByRole("menuitem", { name: "Switch light / dark mode" }).click();
  await assertNoOverflow(page);

  await samContext.close();
});

test("an unknown Group Scout room link shows a helpful not-found state", async ({ page }) => {
  await page.goto("/g/AAAAAAAAAAAAAAAAAAAAAA");
  await expect(
    page.getByRole("heading", { name: "That Group Scout room is not here" }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Start a new Group Room" })).toBeVisible();
  await assertNoOverflow(page);
});
