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
  // A short screen pages the dates instead of scrolling them. The last page shows the last date.
  const next = sheet.getByRole("button", { name: "Next page" });
  while ((await next.count()) && (await next.isEnabled())) await next.click();
  await expect(sheet.locator(".other-chips a").last()).toBeInViewport();
  // The last dates keep the details' 16px of space above Tickets.
  const lastDate = (await sheet
      .locator(".other-chips a")
      .last()
      .boundingBox())!,
    stub = (await sheet.locator(".ticket-stub").boundingBox())!;
  expect(stub.y - (lastDate.y + lastDate.height)).toBeGreaterThanOrEqual(15);
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

test("a festival's whole Lineup pages without scrolling, its matches first", async ({
  page,
}, info) => {
  const lineup = [
    "Alesso",
    "DJ Snake",
    ...Array.from({ length: 23 }, (_, n) => `Lineup Artist ${n + 1}`),
  ];
  const festival = {
    concert: {
      ...calvin.poster.recommendations[0].concert,
      id: "countdown",
      name: "Insomniac Countdown",
      artists: lineup.map((name) => ({ name })),
      festival: true,
      presales: [],
    },
    reason: "Big-room festival house with huge drops.",
    score: 3,
    also: [],
    lineup_match: ["Alesso", "DJ Snake"],
  };
  const poster = { recommendations: [festival] };
  const body = [
    ["candidates", calvin.candidates],
    ["poster", poster],
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
    .getByRole("button", {
      name: "Open Ticket for Insomniac Countdown",
      exact: true,
    })
    .click();
  const sheet = page.locator(".ticket-dialog");
  await expect(sheet).toHaveAttribute("data-motion-phase", "open");
  await expect(sheet.getByText("2 Artists you might like")).toBeVisible();
  await sheet.getByRole("button", { name: "Lineup · 25" }).click();
  await expect(sheet.getByRole("button", { name: /^Back to/ })).toBeFocused();

  const frame = sheet.locator(".paged-window");
  const rows = sheet.locator(".lineup-all li");
  await expect(rows).toHaveCount(25);
  await expect(rows.first()).toHaveAttribute("data-match", "true");
  await expect(rows.nth(1)).toHaveAttribute("data-match", "true");
  await expect(rows.nth(2)).not.toHaveAttribute("data-match", "true");
  expect(
    await frame.evaluate((e) => e.scrollHeight - e.clientHeight),
  ).toBeLessThanOrEqual(1);

  // Whatever shows sits wholly inside the pane: nothing is cut off at either edge.
  const shown = () =>
    frame.evaluate((e) => {
      const box = e.getBoundingClientRect();
      return [...e.querySelectorAll("li")]
        .map((li) => li.getBoundingClientRect())
        .filter((r) => r.right > box.left + 1 && r.left < box.right - 1)
        .map(
          (r) =>
            r.left >= box.left - 1 &&
            r.right <= box.right + 1 &&
            r.bottom <= box.bottom + 1,
        );
    });
  const pager = sheet.locator(".pager span");
  await expect(pager).toHaveText(/^1 of [2-9]$/);
  const first = await shown();
  expect(first.length).toBeGreaterThan(0);
  expect(first.every(Boolean)).toBe(true);

  await sheet.getByRole("button", { name: "Next page" }).click();
  await expect(pager).toHaveText(/^2 of /);
  await expect(async () => {
    const second = await shown();
    expect(second.length).toBeGreaterThan(0);
    expect(second.every(Boolean)).toBe(true);
  }).toPass();
  await expect(
    sheet.getByRole("button", { name: "Save", exact: true }),
  ).toBeInViewport();
  await page.screenshot({ path: info.outputPath("lineup.png") });
});
