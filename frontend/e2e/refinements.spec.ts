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
  await page.reload();
  await page.goto("/saved");
  await expect(
    page.getByText("Nothing saved yet.", { exact: false }),
  ).toBeVisible();
});

test("expanding eight dates keeps the Ticket and photo frame fixed while details scroll", async ({
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
  const before = await sheet.boundingBox(),
    photo = await page.locator(".dialog-photo").boundingBox();
  await sheet.getByText("8 more dates", { exact: true }).click();
  const after = await sheet.boundingBox(),
    afterPhoto = await page.locator(".dialog-photo").boundingBox();
  for (const key of ["x", "y", "width", "height"] as const) {
    expect(Math.abs(before![key] - after![key])).toBeLessThanOrEqual(1);
    expect(Math.abs(photo![key] - afterPhoto![key])).toBeLessThanOrEqual(1);
  }
  await expect(sheet.locator(".other-chips a")).toHaveCount(8);
  await sheet.locator(".other-chips a").last().scrollIntoViewIfNeeded();
  await expect(sheet.locator(".other-chips a").last()).toBeVisible();
  await expect(
    sheet.getByRole("button", { name: "Close Ticket" }),
  ).toBeInViewport();
  await page.screenshot({ path: info.outputPath("expanded-dates.png") });
  await sheet
    .getByText("8 more dates", { exact: true })
    .scrollIntoViewIfNeeded();
  await sheet.getByText("8 more dates", { exact: true }).click();
  const collapsedAgain = await sheet.boundingBox();
  expect(Math.abs(collapsedAgain!.height - before!.height)).toBeLessThanOrEqual(
    1,
  );
  await page.keyboard.press("Escape");
  await expect(sheet).toHaveCount(0);
});
