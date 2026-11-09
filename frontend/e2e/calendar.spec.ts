import { readFile } from "node:fs/promises";

import { expect, test, type Download, type Page } from "@playwright/test";

async function openTicket(page: Page, artist: string) {
  await page.goto("/");
  await page.getByRole("textbox", { name: "Search", exact: true }).fill("UKG in SF");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.locator(".card-open").first().waitFor({ state: "visible" });
  await page.getByRole("button", { name: `Open Ticket for ${artist}` }).click();
  await expect(page.locator(".ticket-dialog")).toHaveCSS("opacity", "1");
}

async function addFromKeyboard(page: Page, artist: string): Promise<{ download: Download; file: string }> {
  const button = page.getByRole("button", { name: `Add to calendar for ${artist}` });
  await button.focus();
  await expect(button).toBeFocused();
  const downloading = page.waitForEvent("download");
  await page.keyboard.press("Enter");
  const download = await downloading;
  return { download, file: await readFile((await download.path())!, "utf8") };
}

test("a Ticket adds its Concert to a calendar from the keyboard, with no request", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await openTicket(page, "Contract Artist");
  const button = page.getByRole("button", { name: "Add to calendar for Contract Artist" });
  expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44);

  const requests: string[] = [];
  page.on("request", (request) => requests.push(request.url()));
  const { download, file } = await addFromKeyboard(page, "Contract Artist");
  expect(requests.filter((url) => !url.startsWith("blob:"))).toEqual([]);

  expect(download.suggestedFilename()).toBe("contract-concert-one.ics");
  expect(file).toContain("BEGIN:VCALENDAR\r\n");
  expect(file).toContain("SUMMARY:Contract Concert One\r\n");
  expect(file).toContain("LOCATION:Source Hall\\, San Francisco\\, CA\r\n");
  expect(file).toContain("URL:https://tickets.example/one\r\n");
  // The source reports 7:30 PM and no zone, so the time stays on that clock with no end.
  expect(file).toMatch(/\r\nDTSTART:\d{8}T193000\r\n/);
  expect(file).not.toMatch(/DTEND|DURATION/);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("a Concert with no time becomes an all-day event", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await openTicket(page, "Second Contract Artist");
  const { file } = await addFromKeyboard(page, "Second Contract Artist");
  expect(file).toMatch(/\r\nDTSTART;VALUE=DATE:\d{8}\r\n/);
  expect(file).not.toMatch(/DTEND|DURATION|TZID/);
});

test("a Saved Concert adds itself to a calendar", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await openTicket(page, "Contract Artist");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("button", { name: "Unsave", exact: true })).toBeVisible();

  await page.goto("/saved");
  const button = page.getByRole("button", { name: "Add to calendar for Contract Artist" });
  await expect(button).toBeVisible();
  expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const { file } = await addFromKeyboard(page, "Contract Artist");
  expect(file).toContain("SUMMARY:Contract Concert One\r\n");
  expect(file).toMatch(/\r\nDTSTART:\d{8}T193000\r\n/);
});
