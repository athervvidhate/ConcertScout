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

test("eight dates unfold within the viewport without enlarging the photo or scrolling the details", async ({
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
  await sheet
    .getByRole("button", { name: "8 more dates", exact: true })
    .click();
  // Sample the actual frame on successive paints, rather than only its final geometry.
  const frames = await sheet.evaluate(async (e) => {
    const values: { at: number; height: number }[] = [];
    const until = performance.now() + 700;
    let at = performance.now();
    while (at < until) {
      values.push({ at, height: e.getBoundingClientRect().height });
      at = await new Promise<number>(requestAnimationFrame);
    }
    return values;
  });
  const heights = frames.map((frame) => frame.height);
  const after = await sheet.boundingBox(),
    afterPhoto = await page.locator(".dialog-photo").boundingBox();
  expect(afterPhoto!.width).toBeCloseTo(photo!.width, 0);
  expect(afterPhoto!.height).toBeLessThanOrEqual(photo!.height + 1);
  if (info.project.name === "desktop") {
    expect(afterPhoto!.height).toBeCloseTo(photo!.height, 0);
    expect(after!.height).toBeGreaterThan(before!.height + 40);
    expect(
      heights.some(
        (height) => height > before!.height + 5 && height < after!.height - 5,
      ),
    ).toBe(true);
    // Speed, not per-frame distance: a busy machine drops frames without the sheet jumping.
    // The limit is 70px per 60fps frame.
    expect(
      Math.max(
        ...frames
          .slice(1)
          .map(
            (frame, i) =>
              Math.abs(frame.height - frames[i].height) /
              Math.max(frame.at - frames[i].at, 1000 / 60),
          ),
      ),
    ).toBeLessThan(70 / (1000 / 60));
  }
  await expect(sheet.locator(".other-chips a")).toHaveCount(8);
  await expect(sheet.locator(".other-chips a").last()).toBeInViewport();
  await expect(
    sheet.getByRole("button", { name: "Save", exact: true }),
  ).toBeInViewport();
  expect(
    await sheet
      .locator(".dialog-details")
      .evaluate((e) => e.scrollHeight - e.clientHeight),
  ).toBeLessThanOrEqual(1);
  await expect(
    sheet.getByRole("button", { name: "Close Ticket" }),
  ).toBeInViewport();
  await page.screenshot({ path: info.outputPath("expanded-dates.png") });
  await sheet
    .getByRole("button", { name: "8 more dates", exact: true })
    .click();
  await expect
    .poll(async () =>
      Math.abs((await sheet.boundingBox())!.height - before!.height),
    )
    .toBeLessThanOrEqual(1);
  await expect
    .poll(
      async () => (await sheet.locator(".other-content").boundingBox())!.height,
    )
    .toBeLessThan(1);
  // A clipped descendant still has a DOM box; prove it is out of keyboard navigation.
  await page.keyboard.press("Tab");
  await expect(
    sheet.getByRole("link", {
      name: `Tickets for ${calvin.poster.recommendations[0].concert.name}`,
      exact: true,
    }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(sheet).toHaveCount(0);
});
