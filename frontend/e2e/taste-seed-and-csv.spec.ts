import { expect, type Page, test } from "@playwright/test";

import { API_URL } from "./ports";

test.use({ reducedMotion: "reduce" });
test.beforeEach(({ isMobile }, info) => {
  test.skip(isMobile && !info.tags.includes("@phone"), "Width does not change this behavior");
});

async function noOverflow(page: Page) {
  const { scroll, client } = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(scroll).toBeLessThanOrEqual(client);
}

test(
  "Visual Taste Seed picker reaches 10+ Artists from Make it yours via autocomplete, keyboard nav, and related chips",
  { tag: "@phone" },
  async ({ page }) => {
    await page.goto("/");

    // Reachable directly from Make it yours on home.
    const yours = page.getByRole("region", { name: "Make it yours" });
    await yours.getByRole("button", { name: "Pick Artists" }).click();

    const dialog = page.getByRole("dialog", { name: "Your Taste" });
    await expect(dialog).toBeVisible();

    const searchInput = dialog.getByRole("combobox", { name: "Search for an Artist" });
    await expect(searchInput).toBeVisible();

    // Pick first Artist using keyboard navigation (ArrowDown + Enter).
    await searchInput.fill("Khru");
    const listbox = dialog.getByRole("listbox", { name: "Artist suggestions" });
    await expect(listbox.getByRole("option", { name: "Khruangbin" })).toBeVisible();
    await searchInput.press("ArrowDown");
    await searchInput.press("Enter");

    const selectedList = dialog.getByRole("list", { name: "Selected Artists" });
    await expect(selectedList.getByRole("listitem")).toHaveCount(1);
    await expect(selectedList).toContainText("Khruangbin");

    // Pick two more Artists via autocomplete click.
    await searchInput.fill("Bono");
    await listbox.getByRole("option", { name: "Bonobo" }).click();
    await searchInput.fill("Tame");
    await listbox.getByRole("option", { name: "Tame Impala" }).click();
    await expect(selectedList.getByRole("listitem")).toHaveCount(3);
    // Styled, not bare text: picks sit side by side and the Add button is a full touch target.
    const [first, second] = await selectedList.getByRole("listitem").evaluateAll((items) =>
      items.slice(0, 2).map((item) => item.getBoundingClientRect().top),
    );
    expect(first).toBe(second);
    expect((await dialog.getByRole("button", { name: "Add", exact: true }).boundingBox())!.height).toBeGreaterThanOrEqual(48);

    // Tap related follow-up chips ("Also like...") to reach 10+ Artists rapidly.
    const relatedRegion = dialog.getByRole("region", { name: "Also like" });
    await expect(relatedRegion).toBeVisible();
    const relatedButtons = relatedRegion.getByRole("button");
    await expect(relatedButtons.first()).toBeVisible();

    while ((await selectedList.getByRole("listitem").count()) < 10) {
      await expect(relatedButtons.first()).toBeVisible();
      await relatedButtons.first().click();
    }

    await expect(selectedList.getByRole("listitem")).toHaveCount(10);
    await expect(dialog.getByText("10 Artists picked. Save, or keep adding.")).toBeVisible();
    await noOverflow(page);

    await dialog.getByRole("button", { name: "Save Taste" }).click();
    await expect(dialog.getByText("Using 10 Artists from your Taste picks.")).toBeVisible();

    await dialog.getByRole("button", { name: "Close", exact: true }).click();
    const request = page.waitForRequest((r) => r.url().endsWith("/search"));
    await page.getByRole("textbox", { name: "Search", exact: true }).fill("SF");
    const searchButton = page.getByRole("button", { name: "Search", exact: true });
    await expect(searchButton).toBeEnabled();
    await searchButton.click();
    const sent = (await request).postDataJSON();
    expect(sent.taste).toHaveLength(10);
    // The newest picks lead, so a Search seeds from what was just added.
    expect(sent.taste.slice(-3)).toEqual(["Tame Impala", "Bonobo", "Khruangbin"]);
  },
);

test(
  "Exportify and TuneMyMusic files parse strictly in the browser with clear provenance and Update import",
  { tag: "@phone" },
  async ({ page }) => {
    await page.goto("/");
    const outboundPosts: string[] = [];
    page.on("request", (req) => {
      if (req.url().startsWith(API_URL) && req.method() === "POST") {
        outboundPosts.push(req.url());
      }
    });

    // Switch to dark theme to verify the Taste panel and presets in dark palette too.
    await page.getByRole("button", { name: "Menu" }).click();
    await page.getByRole("menuitem", { name: "Switch light / dark mode" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-mode", "dark");
    await page.getByRole("button", { name: "Menu" }).click();
    await page.getByRole("menuitem", { name: /^Your Taste/ }).click();

    const dialog = page.getByRole("dialog", { name: "Your Taste" });
    await dialog.getByRole("button", { name: "Import a playlist" }).click();

    const exportifyCsv = [
      "Track URI,Track Name,Artist URI(s),Artist Name(s),Album Name",
      'spotify:track:SECRET_TRACK_1,Secret Song 1,"spotify:artist:1; spotify:artist:2","Khruangbin; Leon Bridges",Texas Sun',
      "spotify:track:SECRET_TRACK_2,Secret Song 2,spotify:artist:1,Khruangbin,Mordechai",
      "spotify:track:SECRET_TRACK_3,Secret Song 3,spotify:artist:3,Stray Novelty Act,Promo",
    ].join("\n");

    await dialog.getByLabel(/Drop a CSV or TXT file/).setInputFiles({
      name: "liked_songs_exportify.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(exportifyCsv),
    });

    await expect(dialog.getByText(/from your Exportify CSV, most played first/)).toBeVisible();
    const importedList = dialog.getByRole("list", { name: "Imported Artists" });
    await expect(importedList.getByRole("listitem")).toHaveCount(3);
    // Remove stray entry before saving.
    await dialog.getByRole("button", { name: "Remove Stray Novelty Act" }).click();
    await expect(importedList.getByRole("listitem")).toHaveCount(2);
    await noOverflow(page);

    await dialog.getByRole("button", { name: "Save Taste" }).click();
    await expect(dialog.getByText("Using 2 Artists from your Exportify CSV file.")).toBeVisible();
    await expect(dialog.getByText(/Imported .*File import on this device \(not a live Spotify connection\)/)).toBeVisible();
    // Raw file stayed completely client-side: zero POSTs to the API.
    expect(outboundPosts).toEqual([]);

    // Update import with a TuneMyMusic TXT export.
    await dialog.getByRole("button", { name: "Update import" }).click();
    const tuneMyMusicTxt = [
      "Bonobo - PRIVATE_TMM_TRACK_1",
      "Bonobo - PRIVATE_TMM_TRACK_2",
      "Four Tet - PRIVATE_TMM_TRACK_3",
    ].join("\n");
    await dialog.getByLabel(/Drop a CSV or TXT file/).setInputFiles({
      name: "spotify_tunemymusic.txt",
      mimeType: "text/plain",
      buffer: Buffer.from(tuneMyMusicTxt),
    });

    await expect(dialog.getByText(/from your TuneMyMusic TXT/)).toBeVisible();
    await dialog.getByRole("button", { name: "Save Taste" }).click();
    await expect(dialog.getByText("Using 2 Artists from your TuneMyMusic file.")).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Update import" })).toBeVisible();
    expect(outboundPosts).toEqual([]);

    // Confirm only ranked Artist names leave the browser on Search.
    await dialog.getByRole("button", { name: "Close", exact: true }).click();
    const request = page.waitForRequest((r) => r.url().endsWith("/search"));
    await page.getByRole("textbox", { name: "Search", exact: true }).fill("SF");
    const searchButton = page.getByRole("button", { name: "Search", exact: true });
    await expect(searchButton).toBeEnabled();
    await searchButton.click();
    const sent = (await request).postDataJSON();
    expect(sent.taste).toEqual(["Bonobo", "Four Tet"]);
    expect(JSON.stringify(sent)).not.toMatch(/SECRET_TRACK|PRIVATE_TMM_TRACK|spotify:track/);
  },
);
