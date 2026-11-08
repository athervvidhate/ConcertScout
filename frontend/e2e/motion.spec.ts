import { expect, test, type Page } from "@playwright/test";
import { HOW_EXAMPLE } from "../lib/how-example";
import { RECORDED_SEARCH } from "./fixtures/khruangbin";

test.use({ video: "on" });

async function panelSizes(page: Page) {
  return page
    .locator("[data-how-panel]")
    .evaluateAll((els) =>
      els.map((e) => Math.round(e.getBoundingClientRect().height)),
    );
}

test("How replays typed words, staggered names, narrowing and a coordinated reset without shifting panels", async ({
  page,
}, info) => {
  test.setTimeout(40_000);
  await page.goto("/");
  await page.locator(".how").scrollIntoViewIfNeeded();
  await expect(page.locator(".how")).toHaveAttribute("data-phase", "typing");
  await expect
    .poll(async () => {
      const text = await page.locator("[data-typed]").textContent();
      return !!text && text.length > 0 && text.length < HOW_EXAMPLE.text.length;
    })
    .toBe(true);
  const initial = await panelSizes(page);
  await page.screenshot({ path: info.outputPath("how-typing.png") });
  await expect(page.locator(".how")).toHaveAttribute(
    "data-phase",
    "candidates",
  );
  await expect
    .poll(() => page.locator("[data-count]").textContent())
    .not.toBe("0");
  await expect
    .poll(() =>
      page
        .locator(".demo-names .name")
        .evaluateAll((els) =>
          els
            .map((e) => Number(getComputedStyle(e).opacity))
            .some((n) => n > 0 && n < 1),
        ),
    )
    .toBe(true);
  await page.waitForFunction(
    () =>
      document.querySelector(".how")?.getAttribute("data-phase") === "picks" &&
      [...document.querySelectorAll(".demo-pick")].some(
        (e) => Number(getComputedStyle(e).opacity) > 0,
      ),
  );
  await expect(page.locator("[data-count]")).toHaveText(
    String(HOW_EXAMPLE.candidates!.total),
  );
  await expect(page.locator(".demo-names .name:not(.pick)").first()).toHaveCSS(
    "opacity",
    "0.25",
    { timeout: 100 },
  );
  await expect(page.locator(".how")).toHaveAttribute("data-phase", "hold");
  await expect(page.locator(".demo-names .name.pick")).toHaveCount(3);
  await expect(page.locator(".demo-names .name:not(.pick)").first()).toHaveCSS(
    "opacity",
    "0.25",
  );
  await expect(page.locator(".demo-why")).toContainText(
    HOW_EXAMPLE.poster.recommendations[0].reason!,
  );
  expect(await panelSizes(page)).toEqual(initial);
  await page.screenshot({ path: info.outputPath("how-picked.png") });
  await expect(page.locator(".how")).toHaveAttribute("data-phase", "reset");
  await expect
    .poll(() =>
      page
        .locator("[data-demo-part]")
        .evaluateAll((els) =>
          els.every((e) => Number(getComputedStyle(e).opacity) < 0.8),
        ),
    )
    .toBe(true);
  expect(
    await page
      .locator("[data-how-panel]")
      .evaluateAll((els) =>
        els.every((e) => getComputedStyle(e).opacity === "1"),
      ),
  ).toBe(true);
  await expect(page.locator(".how")).toHaveAttribute("data-phase", "typing");
  expect(await panelSizes(page)).toEqual(initial);
  await page.evaluate(() => scrollTo(0, 0));
  const phase = await page.locator(".how").getAttribute("data-phase");
  await page.waitForTimeout(1700);
  await expect(page.locator(".how")).toHaveAttribute("data-phase", phase!);
});

test("reduced motion shows the complete How replay without typing or looping", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.locator(".how").scrollIntoViewIfNeeded();
  await expect(page.locator("[data-typed]")).toHaveText(HOW_EXAMPLE.text);
  await expect(page.locator(".how")).toHaveAttribute("data-phase", "hold");
  await expect(page.locator(".demo-names .pick")).toHaveCount(3);
  await expect(page.locator(".demo-pick")).toHaveCount(3);
  await page.waitForTimeout(1100);
  await expect(page.locator(".how")).toHaveAttribute("data-phase", "hold");
  await expect(page.locator(".hero-flap .split-flap-display")).toHaveCount(0);
  expect(errors).toEqual([]);
});

async function recordedSearch(page: Page) {
  const body = [
    ["status", { step: "rank", message: "Choosing the closest Concerts" }],
    ["interpreted", RECORDED_SEARCH.interpreted],
    ["candidates", RECORDED_SEARCH.candidates],
    ["poster", RECORDED_SEARCH.poster],
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
    .fill(RECORDED_SEARCH.text);
  await page.getByRole("button", { name: "Search", exact: true }).click();
}

test("picks travel as complete pills into revealed cards; Ticket opens and folds back to the exact photo frame", async ({
  page,
}, info) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await recordedSearch(page);
  await expect(page.locator(".run-card")).toHaveAttribute(
    "data-motion-phase",
    "picks",
  );
  await expect(page.locator(".run-card .pick")).toHaveCount(3);
  await expect(page.locator(".name-flight").first()).toBeVisible();
  await expect(page.locator(".name-flight .as-title").first()).toContainText(
    "Rhye",
  );
  await expect(page.locator(".name-flight")).toHaveCount(0);
  const source = page.locator(".concert-card .card-photo").first();
  await source.scrollIntoViewIfNeeded();
  const before = await source.boundingBox();
  await page.locator(".card-open").first().click();
  await expect(page.locator(".photo-flight")).toBeVisible();
  await page.screenshot({ path: info.outputPath("ticket-photo-travel.png") });
  await expect(page.locator(".ticket-dialog")).toHaveAttribute(
    "data-motion-phase",
    "unfolding",
  );
  await page.screenshot({ path: info.outputPath("ticket-unfolding.png") });
  await expect(page.locator(".ticket-dialog")).toHaveAttribute(
    "data-motion-phase",
    "open",
  );
  await expect(page.locator(".photo-flight")).toHaveCount(0);
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.locator(".ticket-dialog .save-action")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.locator(".nav-saved .saved-count")).toHaveText("1");
  await expect(page.locator(".ticket-dialog .save-fill")).toHaveCSS(
    "clip-path",
    /circle\(150%/,
  );
  await page.screenshot({ path: info.outputPath("ticket-saved.png") });
  await page.getByRole("button", { name: "Close Ticket" }).click();
  await expect(page.locator(".ticket-dialog")).toHaveAttribute(
    "data-motion-phase",
    "closing",
  );
  await expect(page.locator(".photo-flight")).toBeVisible();
  await expect(
    page.getByRole("dialog", { name: "Ticket for Rhye", exact: true }),
  ).toHaveCount(0);
  await expect(page.locator(".photo-flight")).toHaveCount(0);
  const after = await source.boundingBox();
  for (const key of ["x", "y", "width", "height"] as const)
    expect(Math.abs(after![key] - before![key])).toBeLessThanOrEqual(1);
  await expect(source.locator("img")).toHaveCSS("opacity", "1");
  await expect(page.locator(".card-open").first()).toBeFocused();
  await page.getByRole("button", { name: "List view" }).click();
  await expect(page.locator(".concerts-list .concert-card")).toHaveCount(3);
  await page.locator(".card-open").first().click();
  await expect(page.locator(".ticket-dialog")).toHaveAttribute(
    "data-motion-phase",
    "open",
  );
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("dialog", { name: "Ticket for Rhye", exact: true }),
  ).toHaveCount(0);
});

test("Ticket interruption restores photos and focus; view arrows persist and the solo name also travels", async ({
  page,
}) => {
  await recordedSearch(page);
  await expect(page.locator(".name-flight")).toHaveCount(0);
  await page.locator(".card-open").first().click();
  await expect(page.locator(".photo-flight")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.locator(".ticket-dialog")).toHaveCount(0);
  await expect(page.locator(".photo-flight")).toHaveCount(0);
  await expect(page.locator(".card-open").first()).toBeFocused();
  await expect(page.locator(".card-photo img").first()).toHaveCSS(
    "opacity",
    "1",
  );
  await page.locator(".card-open").first().click();
  await expect(page.locator(".ticket-dialog")).toHaveAttribute(
    "data-motion-phase",
    "unfolding",
  );
  await page.keyboard.press("Escape");
  await expect(page.locator(".ticket-dialog")).toHaveCount(0);
  await expect(page.locator(".photo-flight")).toHaveCount(0);
  await expect(page.locator(".card-photo img").first()).toHaveCSS(
    "opacity",
    "1",
  );
  await page.getByRole("button", { name: "Grid view" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("button", { name: "List view" })).toBeFocused();
  await expect(page.locator(".concerts-list .concert-card")).toHaveCount(3);
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem("concert-scout-view")))
    .toBe("list");
  await page.getByRole("button", { name: "Grid view" }).click();
  const one = {
    ...RECORDED_SEARCH.poster,
    recommendations: RECORDED_SEARCH.poster.recommendations.slice(0, 1),
  };
  const body = [
    ["candidates", RECORDED_SEARCH.candidates],
    ["poster", one],
    ["done", {}],
  ]
    .map(
      ([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`,
    )
    .join("");
  await page.route("**/search", (route) =>
    route.fulfill({ contentType: "text/event-stream", body }),
  );
  await page
    .getByRole("textbox", { name: "Search", exact: true })
    .fill("Rhye in Chicago");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.locator(".solo")).toHaveCount(1);
  await expect(page.locator(".name-flight .as-title")).toHaveText("Rhye");
  await expect(page.locator(".name-flight")).toHaveCount(0);
  await page.getByRole("link", { name: "Concert Scout", exact: true }).click();
  await expect(page.locator(".headline")).toBeVisible();
  await expect(page.locator(".fluid-poster")).toHaveCount(0);
  await expect(page.locator(".photo-flight,.name-flight")).toHaveCount(0);
});

test("home enters in stages and library flaps replace the hero within clipped halves", async ({
  page,
}, info) => {
  await page.route("**/examples", (route) =>
    route.fulfill({ json: { examples: [HOW_EXAMPLE] } }),
  );
  await page.goto("/");
  await expect
    .poll(() =>
      page.locator(".search-bar").evaluate((e) => {
        const n = Number(getComputedStyle(e).opacity);
        return n > 0 && n < 1;
      }),
    )
    .toBe(true);
  await expect
    .poll(() =>
      page.locator(".strip-tile").evaluateAll((els) =>
        els.some((e) => {
          const n = Number(getComputedStyle(e).opacity);
          return n > 0 && n < 1;
        }),
      ),
    )
    .toBe(true);
  await expect(page.locator(".search-bar")).toHaveCSS("opacity", "1");
  await expect(page.locator(".hero-flap")).toHaveAttribute(
    "data-hero-index",
    "1",
  );
  await page.waitForFunction(() =>
    [
      ...document.querySelectorAll(
        ".hero-flap .split-flap-part.final:not(.idle)",
      ),
    ].some((el) =>
      el
        .getAnimations()
        .some(
          (a) =>
            typeof a.currentTime === "number" &&
            a.currentTime > 80 &&
            a.currentTime < 300,
        ),
    ),
  );
  await expect(page.locator(".hero-line")).toHaveCount(0);
  expect(
    await page
      .locator(".hero-flap .split-flap-part")
      .evaluateAll((els) =>
        els.every((e) => getComputedStyle(e).overflow === "hidden"),
      ),
  ).toBe(true);
  await page.screenshot({ path: info.outputPath("hero-flapping.png") });
});
