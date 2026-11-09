import { expect, test, type Page } from "@playwright/test";
import { RECORDED_SEARCH as recording } from "./fixtures/khruangbin";
import calvin from "../lib/how-recording.json";

async function search(page: Page) {
  const body = [
    ["interpreted", recording.interpreted],
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

test("example words clear on focus and return only to an empty unfocused home input", async ({
  page,
}) => {
  await page.goto("/");
  const input = page.getByRole("textbox", { name: "Search", exact: true });
  await expect(input).toHaveAttribute("placeholder", /.+/);
  await input.focus();
  await expect(input).not.toHaveAttribute("placeholder", /.+/, {
    timeout: 3000,
  });
  await input.fill("My own Search");
  await input.blur();
  await expect(input).toHaveValue("My own Search");
  await expect(input).not.toHaveAttribute("placeholder", /.+/);
  await input.fill("");
  await input.blur();
  await expect(input).toHaveAttribute("placeholder", /.+/);
});

test("photo bookmark and Ticket toggle the same saved Concert without opening or closing the Ticket", async ({
  page,
}) => {
  await search(page);
  const photo = page.getByRole("button", { name: "Save Rhye", exact: true });
  await expect(photo).toBeVisible({ timeout: 5000 });
  await photo.click();
  await expect(
    page.getByRole("dialog", { name: "Ticket for Rhye", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Unsave Rhye", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page
    .getByRole("button", { name: "Open Ticket for Rhye", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Ticket for Rhye",
    exact: true,
  });
  await expect(dialog).toHaveAttribute("data-motion-phase", "open");
  await dialog.getByRole("button", { name: "Unsave", exact: true }).click();
  await expect(
    dialog.getByRole("button", { name: "Save", exact: true }),
  ).toHaveAttribute("aria-pressed", "false");
  await dialog.getByRole("button", { name: "Save", exact: true }).click();
  await expect(
    dialog.getByRole("button", { name: "Unsave", exact: true }),
  ).toBeEnabled();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await page.getByRole("button", { name: "Unsave Rhye", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Save Rhye", exact: true }),
  ).toHaveAttribute("aria-pressed", "false");
  await expect(page.locator(".poster-notice")).toHaveText(
    "Rhye removed from Saved Concerts.",
  );
  await expect(page.locator(".poster-notice")).toHaveCount(0, {
    timeout: 6000,
  });
  await page.reload();
  await page.goto("/saved");
  await expect(
    page.getByText("Nothing saved yet.", { exact: false }),
  ).toBeVisible();
});

test("eight dates swap in without resizing the Ticket, its photo or scrolling", async ({
  page,
}, info) => {
  const body = [
    ["candidates", calvin.candidates],
    ["poster", calvin.poster],
    ["done", {}],
  ]
    .map(
      ([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`,
    )
    .join("");
  await page.route("**/search", (r) =>
    r.fulfill({ contentType: "text/event-stream", body }),
  );
  await page.goto("/");
  await page
    .getByRole("textbox", { name: "Search", exact: true })
    .fill(calvin.text);
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page
    .getByRole("button", { name: "Open Ticket for Calvin Harris", exact: true })
    .click();
  const sheet = page.locator(".ticket-dialog");
  await expect(sheet).toHaveAttribute("data-motion-phase", "open");
  const before = (await sheet.boundingBox())!,
    photo = (await page.locator(".dialog-photo").boundingBox())!;
  const more = sheet.getByRole("button", { name: "8 more dates", exact: true });
  await more.click();
  // Sample every paint while the dates swap in: the Ticket and its photograph never change size.
  const frames = await sheet.evaluate(async (e) => {
    const image = e.querySelector(".dialog-photo")!;
    const values: number[][] = [];
    const until = performance.now() + 700;
    while (performance.now() < until) {
      const a = e.getBoundingClientRect(),
        b = image.getBoundingClientRect();
      values.push([a.height, b.width, b.height]);
      await new Promise(requestAnimationFrame);
    }
    return values;
  });
  for (const [height, width, photoHeight] of frames) {
    expect(Math.abs(width - photo.width)).toBeLessThanOrEqual(1);
    expect(Math.abs(photoHeight - photo.height)).toBeLessThanOrEqual(1);
    if (info.project.name === "desktop")
      expect(Math.abs(height - before.height)).toBeLessThanOrEqual(1);
  }
  const back = sheet.getByRole("button", { name: /^Back to/ });
  await expect(back).toBeFocused();
  await expect(sheet.locator(".other-chips a")).toHaveCount(8);
  await expect(sheet.locator(".other-chips a").last()).toBeInViewport();
  await expect(
    sheet.getByRole("button", { name: "Save", exact: true }),
  ).toBeInViewport();
  if (info.project.name === "desktop")
    for (const pane of [".dialog-details", ".ticket-main"])
      expect(
        await sheet
          .locator(pane)
          .evaluate((e) => e.scrollHeight - e.clientHeight),
      ).toBeLessThanOrEqual(1);
  await expect(
    sheet.getByRole("button", { name: "Close Ticket" }),
  ).toBeInViewport();
  await page.screenshot({ path: info.outputPath("dates.png") });
  await back.click();
  await expect(more).toBeFocused();
  await expect(sheet.locator(".other-chips a")).toHaveCount(0);
  expect(
    Math.abs((await sheet.boundingBox())!.height - before.height),
  ).toBeLessThanOrEqual(1);
  await page.keyboard.press("Escape");
  await expect(sheet).toHaveCount(0);
});
