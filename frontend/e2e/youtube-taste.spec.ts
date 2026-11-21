import { expect, type Page, test } from "@playwright/test";

test.use({ reducedMotion: "reduce" });
test.beforeEach(({ isMobile }, info) => {
  test.skip(isMobile && !info.tags.includes("@phone"), "Width does not change this behavior");
});

async function openTastePanel(page: Page) {
  await page.getByRole("button", { name: "Menu" }).click();
  await page.getByRole("menuitem", { name: /^Your Taste/ }).click();
  await page.getByRole("button", { name: "Other ways to add your Taste" }).click();
  await page.getByLabel("Import from").selectOption("youtube");
}

async function noOverflow(page: Page) {
  const { scroll, client } = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(scroll).toBeLessThanOrEqual(client);
}

test(
  "YouTube playlist import extracts chips, lets visitors remove stray entries, and sends saved Taste in Search",
  { tag: "@phone" },
  async ({ page }) => {
    await page.goto("/");
    await openTastePanel(page);

    const urlInput = page.getByLabel("YouTube playlist URL");
    await urlInput.fill("https://music.youtube.com/playlist?list=PLcontractPublic123");
    await page.getByRole("button", { name: "Find Artists" }).click();

    const chips = page.getByRole("list", { name: "Extracted Artists" });
    await expect(chips).toBeVisible();
    await expect(chips.getByRole("listitem")).toHaveCount(3);
    await expect(page.getByText(/Found 3 Artists/)).toBeVisible();

    // Remove the stray non-artist entry before saving.
    await page.getByRole("button", { name: "Remove Stray Podcast" }).click();
    await expect(chips.getByRole("listitem")).toHaveCount(2);
    await expect(page.getByText(/Found 2 Artists/)).toBeVisible();
    await noOverflow(page);

    await page.getByRole("button", { name: "Save Taste" }).click();
    await expect(page.getByText("Using 2 Artists from your YouTube playlist.")).toBeVisible();
    // A saved Taste can still come from somewhere else.
    await page.getByRole("button", { name: "Other ways to add your Taste" }).click();
    await expect(page.getByText("Saving from here replaces your 2 Artists.")).toBeVisible();
    await expect(page.getByLabel("Import from")).toBeVisible();

    await page.getByRole("button", { name: "Close", exact: true }).click();
    const request = page.waitForRequest((r) => r.url().endsWith("/search"));
    await page.getByRole("textbox", { name: "Search", exact: true }).fill("SF");
    const searchButton = page.getByRole("button", { name: "Search", exact: true });
    await expect(searchButton).toBeEnabled();
    await searchButton.click();
    const data = (await request).postDataJSON();
    expect(data.taste).toEqual(["Khruangbin", "Tame Impala"]);
  },
);

test("a long playlist grows down the panel instead of scrolling inside it", async ({ page }) => {
  await page.goto("/");
  await openTastePanel(page);
  await page.getByLabel("YouTube playlist URL").fill("https://www.youtube.com/playlist?list=PLcontractLong123");
  await page.getByRole("button", { name: "Find Artists" }).click();

  const chips = page.getByRole("list", { name: "Extracted Artists" });
  await expect(chips.getByRole("listitem")).toHaveCount(50);
  expect(await chips.evaluate((e) => e.scrollHeight - e.clientHeight)).toBeLessThanOrEqual(1);
  const panel = page.locator(".taste-panel");
  expect(await panel.evaluate((e) => e.scrollHeight > e.clientHeight)).toBe(true);
  await page.getByRole("button", { name: "Save Taste" }).scrollIntoViewIfNeeded();
  await expect(page.getByRole("button", { name: "Save Taste" })).toBeInViewport();
});

test("invalid, private, and empty YouTube playlists show actionable inline errors", async ({
  page,
}) => {
  await page.goto("/");
  await openTastePanel(page);

  const urlInput = page.getByLabel("YouTube playlist URL");
  const submit = page.getByRole("button", { name: "Find Artists" });
  const alert = page.locator(".taste-panel [role=alert]");

  await urlInput.fill("https://example.com/not-a-playlist");
  await submit.click();
  await expect(alert).toContainText("YouTube");

  await urlInput.fill("https://www.youtube.com/playlist?list=PLcontractPrivate123");
  await submit.click();
  await expect(alert).toContainText(/private/i);

  await urlInput.fill("https://www.youtube.com/playlist?list=PLcontractEmpty123");
  await submit.click();
  await expect(alert).toContainText(/could not find any Artists/i);
});
